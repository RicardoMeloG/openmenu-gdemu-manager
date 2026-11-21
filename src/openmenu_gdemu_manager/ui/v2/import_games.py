"""Real file/folder inspection with explicit, reversible import selection."""
import logging
from dataclasses import replace
from pathlib import Path,PureWindowsPath
from ...app.logger import logged_operation
from PySide6.QtCore import Qt,Signal,QObject,Slot,QEvent
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QFileDialog,QTableWidget,QTableWidgetItem,QHeaderView,QMessageBox,QLabel,QSizePolicy,QSpacerItem
from ...core.models import RomLibraryEntry
from ...dreamcast.rom_library import inspect_source,is_gdemu_menu_slot
from ...dreamcast.image_integrity import validate_source
from ...config.settings import supported_media_types
from ...dreamcast.sd_writer import MAX_USER_SLOT, source_size
from ...services.sd_slot_transaction import COVER_BYTES_PER_GAME, SPACE_MARGIN_BYTES, folder_size, format_bytes, free_space
from .design import repolish
from ..workers import start_worker
from ..widgets import BusyOverlay
from .design import Button,SelectionCheck,label,clearable_edit
from .catalog import tr


log = logging.getLogger(__name__)

# Inspection results for this session, so picking the same folder again only
# lists it: reading every image header again is what is slow on a mechanical
# disk. An entry is reused only while its files keep the same names, sizes and
# modification times. Values: (fingerprint, entry or None, reason).
_INSPECTION_CACHE={}
_last_folder=''


def clear_inspection_cache():
    _INSPECTION_CACHE.clear()


def _fingerprint(source):
    """Cheap stat-only identity of what inspect/validate read for this source."""
    if source.suffix.lower()=='.gdi':
        # A GDI game is its whole folder: descriptor, tracks and name.txt.
        files=[path for path in source.parent.iterdir() if path.is_file()]
    else:
        files=[source]+[path for path in (source.parent/'name.txt',) if path.is_file()]
    return tuple(sorted((path.name.casefold(),path.stat().st_size,path.stat().st_mtime_ns) for path in files))


class InspectWorker(QObject):
    finished=Signal(object);error=Signal(str)
    # (current, total, game folder); total 0 means the folder is still being listed.
    progress=Signal(int,int,str)
    def __init__(self,paths,supported):super().__init__();self.paths=paths;self.supported=supported
    @logged_operation("inspect_games")
    def run(self):
        try:
            results={}
            # Listing a large folder on a mechanical disk takes a while on its own.
            self.progress.emit(0,0,'')
            sources=[]
            for path in self.paths:
                path=Path(path)
                sources.extend([path] if path.is_file() else [p for p in path.rglob('*') if p.suffix.lower() in ('.gdi','.cdi')])
            reused=0
            for index,source in enumerate(sources,1):
                self.progress.emit(index,len(sources),source.parent.name)
                if is_gdemu_menu_slot(source):continue
                key=(str(source).casefold(),frozenset(self.supported))
                try:fingerprint=_fingerprint(source)
                except OSError:fingerprint=None
                cached=_INSPECTION_CACHE.get(key)
                if fingerprint is not None and cached and cached[0]==fingerprint:
                    reused+=1
                    entry,reason=cached[1],cached[2]
                    # A copy: the dialog marks duplicates on the entries it receives.
                    if entry is not None:results.setdefault(entry.source_path.casefold(),(replace(entry),reason))
                    continue
                entry,reason=self.inspect(source)
                if fingerprint is not None:_INSPECTION_CACHE[key]=(fingerprint,entry,reason)
                if entry is not None:results.setdefault(entry.source_path.casefold(),(replace(entry),reason))
            log.info("Source inspection finished: sources=%s reused=%s", len(sources), reused)
            self.finished.emit(list(results.values()))
        except Exception as exc:
            log.exception("Source inspection failed")
            self.error.emit(str(exc))

    def inspect(self,source):
        """(entry, rejection reason) for one GDI/CDI; entry None when not importable."""
        try:
            entry=inspect_source(source,self.supported)
            if entry is None:return None,''
            # Same measure the save uses to check free space: what will be copied.
            try:entry.size_bytes=source_size(Path(entry.source_path))
            except OSError:entry.size_bytes=0
            reason=''
            try:validate_source(entry.source_path)
            except ValueError as exc:
                log.warning("Source rejected: path=%s reason=%s", entry.source_path, exc)
                reason=str(exc)
            return entry,reason
        except (OSError,ValueError) as exc:
            log.warning("Source inspection failed: path=%s", source, exc_info=True)
            return RomLibraryEntry(name=source.parent.name,media_type=source.suffix[1:].upper(),source_path=str(source)),str(exc)


def warn(parent,heading,details):
    """Warning with a bold heading and a readable width for a multi-line explanation."""
    box=QMessageBox(QMessageBox.Icon.Warning,tr('add_title'),heading,QMessageBox.StandardButton.Ok,parent)
    box.setInformativeText(details)
    # QMessageBox sizes itself to the longest unbroken word; keep the figures on one line each.
    layout=box.layout()
    layout.addItem(QSpacerItem(460,0,QSizePolicy.Policy.Minimum,QSizePolicy.Policy.Expanding),layout.rowCount(),0,1,layout.columnCount())
    box.exec()


class PathLabel(QLabel):
    """One-line source path, shortened in the middle so drive and game folder stay visible."""
    def __init__(self):
        super().__init__('');self.full_text=''
        self.setProperty('muted',True)
        self.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    def set_path(self,text,tooltip):
        self.full_text=text;self.setToolTip(tooltip);self.setAccessibleName(text);self._elide()
    def resizeEvent(self,event):
        super().resizeEvent(event);self._elide()
    def _elide(self):
        self.setText(self.fontMetrics().elidedText(self.full_text,Qt.TextElideMode.ElideMiddle,max(40,self.width()-4)))


class ImportGamesDialog(QDialog):
    selected=Signal(object)
    def __init__(self,settings,games,parent=None):
        super().__init__(parent)
        self.settings,self.games=settings,games
        self.entries=[];self.errors=[];self.checked=[];self.scan_thread=None;self.scan_worker=None
        self._inspecting=False
        self._inspection_error=''
        self.resize(960,620);self.setWindowTitle(tr('add_title'))
        root=QVBoxLayout(self);root.setContentsMargins(20,16,20,16)
        root.addWidget(label(tr('add_title'),heading=True))
        root.addWidget(label(tr('choose_source'),muted=True,wrap=True))
        sources=QHBoxLayout()
        self.files=Button('game_files',self.pick_files);self.folder=Button('game_folder',self.pick_folder)
        sources.addWidget(self.files);sources.addWidget(self.folder)
        # Where the listed games come from, next to the buttons that chose it.
        self.sources=[];self.source_label=PathLabel();self.source_label.setObjectName('import_source')
        sources.addWidget(self.source_label,1);root.addLayout(sources)
        # A folder can hold hundreds of games: filtering only hides rows, it never changes the selection.
        self.filter=clearable_edit('',tr('import_filter'));self.filter.setObjectName('import_filter')
        self.filter.setPlaceholderText(tr('import_filter'));self.filter.textChanged.connect(self.apply_filter);root.addWidget(self.filter)
        self.all=SelectionCheck(tr('all'));self.all.clicked.connect(self.select_all);root.addWidget(self.all)
        self.table=QTableWidget(0,5);self.table.setObjectName('ImportTable')
        self.table.setHorizontalHeaderLabels(['',tr('game'),tr('source_path'),tr('format'),tr('status')])
        # Approved mockup: column titles read as headings, left-aligned like their cells.
        self.table.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.table.verticalHeader().hide();self.table.verticalHeader().setDefaultSectionSize(68)
        self.table.horizontalHeader().setSectionResizeMode(1,QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2,QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0,38);self.table.setColumnWidth(3,90);self.table.setColumnWidth(4,190)
        self.table.cellClicked.connect(self.row_clicked);root.addWidget(self.table,1)
        # Same spinning-disc loading screen as the main window, over the list being filled.
        self.busy=BusyOverlay(self.table);self.table.installEventFilter(self)
        self.feedback=label(tr('choose_source'),muted=True,wrap=True);root.addWidget(self.feedback)
        # Size, free space and free positions are shown before preparing, so an
        # accidental whole-library selection is visible here, not at save time.
        self._capacity()
        self.capacity=label('',muted=True,wrap=True);self.capacity.setObjectName('import_capacity');self.capacity.hide();root.addWidget(self.capacity)
        root.addWidget(label(tr('prepare_real_hint'),muted=True,wrap=True))
        bottom=QHBoxLayout();bottom.addStretch()
        self.cancel=Button('cancel',self.reject);self.prepare=Button('add',self.accept_selection,text=tr('prepare_games'))
        self.prepare.setEnabled(False);bottom.addWidget(self.cancel);bottom.addWidget(self.prepare);root.addLayout(bottom)

    def _capacity(self):
        """Free positions and space of the destination, measured once per dialog."""
        used={game.slot for game in self.games}
        self.free_slots=sum(1 for slot in range(2,MAX_USER_SLOT+1) if slot not in used)
        self.free_bytes=None;self.menu_bytes=0;self.pending_bytes=0
        root=getattr(self.parentWidget(),'root_path',None)
        self.destination=str(root) if root is not None else ''
        if root is None:return
        root=Path(root)
        try:
            self.free_bytes=free_space(root)
            # Room to rebuild menu 01 next to the current one, as the save does.
            self.menu_bytes=folder_size(root/'01')+SPACE_MARGIN_BYTES
            # Games already prepared in this session will use part of that space.
            self.pending_bytes=sum(source_size(Path(game.source_path)) for game in self.games if game.pending_add and game.source_path)
        except OSError:
            self.free_bytes=None

    def margin_bytes(self):
        """Covers for the checked games plus the menu rebuild."""
        return sum(self.checked)*COVER_BYTES_PER_GAME+self.menu_bytes

    def needed_bytes(self):
        return self.selected_bytes()+self.margin_bytes()+self.pending_bytes

    def pick_files(self):
        global _last_folder
        files,_=QFileDialog.getOpenFileNames(self,tr('choose_source'),_last_folder,'Dreamcast (*.gdi *.cdi)')
        if files:
            _last_folder=str(Path(files[0]).parent.parent)
            self.inspect_paths(files)

    def pick_folder(self):
        global _last_folder
        # Start where the last search was, so picking more games from it is quick.
        folder=QFileDialog.getExistingDirectory(self,tr('choose_source'),_last_folder)
        if folder:
            _last_folder=folder
            self.inspect_paths([folder])

    def show_sources(self,paths):
        for path in paths:
            path=str(Path(path))
            if path.casefold() not in {known.casefold() for known in self.sources}:self.sources.append(path)
        if not self.sources:return
        first=self.sources[0];more=len(self.sources)-1
        self.source_label.set_path(tr('source_chosen',path=first) if not more else tr('source_chosen_many',path=first,count=more),
                                   '\n'.join(self.sources))

    def inspect_paths(self,paths):
        if self.scan_thread is not None:return
        self.show_sources(paths)
        # Picked files are the user's choice; a folder is a catalogue to choose
        # from, so its games start unchecked instead of the whole library.
        self._preselect=all(Path(path).is_file() for path in paths)
        self._inspecting=True
        self._inspection_error=''
        self.files.setEnabled(False);self.folder.setEnabled(False);self.prepare.setEnabled(False)
        self.table.setEnabled(False);self.all.setEnabled(False)
        self.feedback.setText(tr('source_scanning'))
        self.busy.show_message(tr('source_scanning'),tr('source_listing'))
        worker=InspectWorker(paths,supported_media_types(self.settings))
        start_worker(worker,'scan_thread','scan_worker',self,self.received,self.failed,extra=[(worker.progress,self.inspection_progress)])
        self.scan_thread.finished.connect(self.inspection_finished)
        parent=self.parentWidget()
        if parent is not None and hasattr(parent,'cover_jobs'):parent.cover_jobs.append(self.scan_thread)

    @Slot(int,int,str)
    def inspection_progress(self,current,total,name):
        self.busy.detail.setText(tr('source_scanning_progress',current=current,total=total,name=name) if total else tr('source_listing'))

    def eventFilter(self,watched,event):
        if watched is self.table and event.type()==QEvent.Type.Resize and not self.busy.isHidden():
            self.busy.resizeEvent(None)
        return super().eventFilter(watched,event)

    @Slot()
    def inspection_finished(self):
        self.busy.clear()
        self._inspecting=False
        self.files.setEnabled(True);self.folder.setEnabled(True);self.table.setEnabled(True)
        self.sync()
        if self._inspection_error:self.feedback.setText(tr('read_failed',reason=self._inspection_error))

    def received(self,records):
        known={entry.source_path.casefold() for entry in self.entries}
        for entry,error in records:
            if entry.source_path.casefold() in known:continue
            known.add(entry.source_path.casefold())
            entry.existing_match=any(entry.name.casefold().strip()==g.name.casefold().strip() or bool(entry.product_id) and entry.product_id==g.product_id for g in self.games)
            self.entries.append(entry);self.errors.append(error)
            self.checked.append(getattr(self,'_preselect',True) and not error and not entry.existing_match)
        self.render()

    def failed(self,message):
        self._inspection_error=message
        self.feedback.setText(tr('read_failed',reason=message))

    def render(self):
        self.table.setRowCount(len(self.entries))
        for row,entry in enumerate(self.entries):
            check=SelectionCheck(name=entry.name);check.setChecked(self.checked[row]);check.setEnabled(not self.errors[row]);check.clicked.connect(lambda value,r=row:self.toggle(r,value))
            self.table.setCellWidget(row,0,check)
            status=tr('verify_source') if self.errors[row] else tr('possible_duplicate') if entry.existing_match else tr('source_cdi_checked') if entry.media_type=='CDI' else tr('source_valid')
            for col,value in ((1,entry.name),(2,entry.source_path),(3,entry.media_type),(4,status)):
                item=QTableWidgetItem(value);item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable);item.setToolTip(self.errors[row] or (tr('source_cdi_scope') if entry.media_type=='CDI' and col==4 else value))
                if col==1:
                    font=item.font();font.setWeight(QFont.Weight.DemiBold);item.setFont(font)
                self.table.setItem(row,col,item)
        self.apply_filter()

    def matches(self,row):
        terms=self.filter.text().casefold().split()
        if not terms:return True
        entry=self.entries[row];source=PureWindowsPath(entry.source_path)
        # Only the game's own folder and file: the shared library path would match every row.
        haystack=' '.join((entry.name,source.parent.name,source.name,entry.media_type)).casefold()
        return all(term in haystack for term in terms)

    def visible_rows(self):
        return [row for row in range(len(self.entries)) if not self.table.isRowHidden(row)]

    def apply_filter(self,*_):
        for row in range(len(self.entries)):self.table.setRowHidden(row,not self.matches(row))
        self.sync()

    def toggle(self,row,value):self.checked[row]=bool(value);self.sync()
    def row_clicked(self,row,col):
        if col!=0 and not self.errors[row]:
            self.checked[row]=not self.checked[row];self.table.cellWidget(row,0).setChecked(self.checked[row]);self.sync()
    def filtering(self):
        return bool(self.filter.text().split())
    def select_targets(self):
        # With a filter, "All" means the games the user is looking at; hidden
        # games keep whatever selection they had.
        rows=self.visible_rows() if self.filtering() else range(len(self.entries))
        return [i for i in rows if not self.errors[i]]
    def select_all(self):
        targets=self.select_targets()
        select=not all(self.checked[i] for i in targets)
        for i in targets:self.checked[i]=select;self.table.cellWidget(i,0).setChecked(select)
        self.sync()
    def sync(self):
        count=sum(self.checked);targets=self.select_targets()
        marked=sum(self.checked[i] for i in targets)
        self.all.setCheckState(Qt.CheckState.Checked if targets and marked==len(targets) else Qt.CheckState.PartiallyChecked if marked else Qt.CheckState.Unchecked)
        hidden=self.hidden_checked()
        # Say when checked games are out of sight, or "All shown (2)" hides why the total is larger.
        caption=(tr('all_visible_hidden',count=len(self.visible_rows()),hidden=hidden) if hidden else tr('all_visible',count=len(self.visible_rows()))) if self.filtering() else tr('all')
        if self.all.text()!=caption:self.all.setText(caption);self.all.setAccessibleName(caption);self.all.updateGeometry()
        problem=self.capacity_problem()
        # Prepare stays available: a selection that does not fit explains itself
        # when pressed instead of leaving a silently disabled button.
        self.all.setEnabled(bool(targets) and not self._inspecting);self.prepare.setEnabled(bool(count) and not self._inspecting)
        if self._inspecting:return
        visible=len(self.visible_rows())
        # Hidden rows stay selected and are still added, so the total selection is always stated.
        self.feedback.setText(tr('detected_games',count=len(self.entries),selected=count) if visible==len(self.entries) else tr('detected_games_filtered',visible=visible,count=len(self.entries),selected=count))
        self.show_capacity(problem)
    def selected_bytes(self):
        return sum(entry.size_bytes for entry,checked in zip(self.entries,self.checked) if checked)
    def hidden_checked(self):
        return sum(1 for row,checked in enumerate(self.checked) if checked and self.table.isRowHidden(row))
    def capacity_problem(self):
        count=sum(self.checked)
        if count>self.free_slots:return tr('selection_too_many',count=count,slots=self.free_slots)
        if self.free_bytes is not None and count and self.needed_bytes()>self.free_bytes:
            return tr('selection_too_big',missing=format_bytes(self.needed_bytes()-self.free_bytes))
        return ''
    def show_capacity(self,problem):
        self.capacity.setVisible(bool(self.entries))
        size=format_bytes(self.selected_bytes())
        summary=(tr('selection_capacity',size=size,margin=format_bytes(self.margin_bytes()),free=format_bytes(self.free_bytes),drive=self.destination,slots=self.free_slots)
                 if self.free_bytes is not None else tr('selection_capacity_slots',size=size,slots=self.free_slots))
        hidden=self.hidden_checked()
        # A problem caused by games the filter hides must say so, or the visible
        # selection looks small enough to fit.
        if problem and hidden:problem+='\n'+tr('selection_hidden',count=hidden)
        self.capacity.setText(summary+('\n'+problem if problem else ''))
        tone='warning' if problem else None
        if self.capacity.property('tone')!=tone:
            self.capacity.setProperty('tone',tone);self.capacity.setProperty('muted',not problem);repolish(self.capacity)
    def capacity_details(self):
        """Full explanation shown when Prepare is pressed with a selection that does not fit."""
        count=sum(self.checked);lines=[]
        if count>self.free_slots:
            lines.append(tr('selection_too_many',count=count,slots=self.free_slots))
        else:
            lines.append(tr('capacity_games',count=count,size=format_bytes(self.selected_bytes())))
            lines.append(tr('capacity_margin',size=format_bytes(self.margin_bytes())))
            if self.pending_bytes:lines.append(tr('capacity_pending',size=format_bytes(self.pending_bytes)))
            lines.append(tr('capacity_needed',size=format_bytes(self.needed_bytes())))
            lines.append(tr('capacity_free',drive=self.destination,size=format_bytes(self.free_bytes)))
            lines.append('');lines.append(tr('capacity_missing',size=format_bytes(self.needed_bytes()-self.free_bytes)))
        hidden=self.hidden_checked()
        if hidden:lines.append(tr('selection_hidden',count=hidden))
        return '\n'.join(lines)
    def accept_selection(self):
        if self._inspecting or self.scan_thread is not None:return
        if self.capacity_problem():
            warn(self,tr('capacity_title'),self.capacity_details());return
        entries=[entry for i,entry in enumerate(self.entries) if self.checked[i] and not self.errors[i]]
        if entries:self.selected.emit(entries);self.accept()
    def reject(self):
        if self.scan_thread is not None:QMessageBox.information(self,self.windowTitle(),tr('close_busy'));return
        super().reject()
    def closeEvent(self,event):
        if self.scan_thread is not None:event.ignore()
        else:super().closeEvent(event)
