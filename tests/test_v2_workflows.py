"""Production V2 contracts. Fixtures use generated images and synthetic discs."""
from pathlib import Path
import threading
import pytest
from PIL import Image
from PySide6.QtCore import Qt,QThread
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QMessageBox
from openmenu_gdemu_manager.core.models import GameItem,Candidate,BulkProposal,RomLibraryEntry
from openmenu_gdemu_manager.ui import main_window as legacy
from openmenu_gdemu_manager.ui.v2.main_window import MainWindowV2
from openmenu_gdemu_manager.ui.v2.bridge import ProductionWorkspace
from openmenu_gdemu_manager.ui.v2.import_games import ImportGamesDialog
from openmenu_gdemu_manager.ui.widgets import GamesTableModel
from openmenu_gdemu_manager.ui.v2 import catalog
from openmenu_gdemu_manager.i18n import load_internal_language,set_language,tr as legacy_tr


@pytest.fixture
def window(monkeypatch,tmp_path):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(legacy,'migrate_legacy_runtime_data',lambda:None)
    monkeypatch.setattr(legacy,'recommended_initial_storage_path',lambda fallback:tmp_path)
    # Fresh portable defaults to the original icon-only preference. V2 must
    # still show the approved icon + label without inheriting its fixed widths.
    monkeypatch.setattr(legacy,'load_settings',lambda:{'ui':{'language':'es','show_button_labels':False}})
    monkeypatch.setattr(legacy,'load_state',lambda path:{})
    monkeypatch.setattr(legacy,'configured_template_dir',lambda _:tmp_path)
    monkeypatch.setattr(legacy,'configured_languages_dir',lambda _:tmp_path)
    def fatal(*args):raise AssertionError(args[-1])
    monkeypatch.setattr(QMessageBox,'critical',fatal)
    w=MainWindowV2();assert w._v2_ready
    w.root_path=tmp_path/'sd';w.root_path.mkdir();w.write_allowed=True
    w.games=[GameItem(2,'Covered',current_cover=tmp_path/'cover.png',product_id='T1234',region='US'),GameItem(3,'Missing',has_placeholder_cover=True,product_id='SLOT003'),GameItem(4,'Another missing',has_placeholder_cover=True)]
    Image.new('RGB',(512,510),'orange').save(tmp_path/'cover.png')
    w.games_by_slot={g.slot:g for g in w.games}
    w.apply_filters();w.show();app.processEvents()
    yield w
    w.games=[];w.cover_host.store.clear();w.close();w.deleteLater();app.processEvents()


def test_bulk_defaults_missing_and_global_all_ignores_filter(window):
    window.toggle_bulk_mode()
    assert window.bulk_checked=={2:False,3:True,4:True}
    window.text_filter.setText('Covered')
    window.toggle_bulk_header_selection()
    assert window.bulk_checked=={2:True,3:True,4:True}
    window.toggle_bulk_header_selection()
    assert not any(window.bulk_checked.values())


def test_setup_declined_pending_changes_preserves_destination_and_games(window, monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import setup
    before=(window.root_path,window.path_edit.text(),list(window.games),window.write_allowed)
    monkeypatch.setattr(window,'_can_abandon',lambda:False)
    def forbidden(*args):raise AssertionError('Setup opened before abandonment approval')
    monkeypatch.setattr(setup,'SetupWizardV2',forbidden)
    window.open_setup_wizard()
    assert (window.root_path,window.path_edit.text(),window.games,window.write_allowed)==before


def test_setup_active_operation_cannot_open_installer(window, monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import setup
    monkeypatch.setattr(window,'operation_running',lambda:True)
    def forbidden(*args):raise AssertionError('Setup opened during active job')
    monkeypatch.setattr(setup,'SetupWizardV2',forbidden)
    window.open_setup_wizard()
    monkeypatch.setattr(window,'operation_running',lambda:False)


def test_setup_new_destination_revokes_old_permissions_before_rescan(window, monkeypatch, tmp_path):
    from openmenu_gdemu_manager.ui.v2 import setup
    from PySide6.QtWidgets import QDialog
    destination=tmp_path/'new-destination';destination.mkdir()
    class Accepted:
        def __init__(self,*args):self.selected_path=destination
        def exec(self):return QDialog.DialogCode.Accepted
    monkeypatch.setattr(setup,'SetupWizardV2',Accepted)
    monkeypatch.setattr(window,'_can_abandon',lambda:True)
    captured=[]
    monkeypatch.setattr(window,'start_scan',lambda:captured.append((window.root_path,list(window.games),window.write_allowed)))
    window.open_setup_wizard()
    assert captured==[(destination,[],False)] and window.games_by_slot=={}


def test_diagnostic_dialog_handoff_waits_for_thread_cleanup(window, monkeypatch):
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    diagnostic=diagnose_storage(window.root_path)
    running=[True];called=[]
    monkeypatch.setattr(window,'operation_running',lambda:running[0])
    monkeypatch.setattr(legacy.MainWindow,'finish_diagnostic',lambda self,d:called.append(d))
    window.finish_diagnostic(diagnostic)
    assert not called and window._pending_diagnostic is diagnostic
    running[0]=False
    window.refresh_after_worker()
    assert called==[diagnostic] and window._pending_diagnostic is None


def test_initial_unrelated_working_directory_opens_destination_choice(window,monkeypatch):
    from pathlib import Path
    window.root_path=Path.cwd()
    window.path_edit.setText(str(window.root_path))
    calls=[]
    monkeypatch.setattr(window,'open_setup_wizard',lambda diagnostic=None:calls.append(diagnostic))
    window.start_scan()
    assert calls==[None]


def test_row_and_checkbox_toggle_once_and_actions_leave_bulk(window,monkeypatch):
    window.toggle_bulk_mode()
    row=0;index=window.games_model.index(row,GamesTableModel.C_NAME)
    QTest.mouseClick(window.table.viewport(),Qt.MouseButton.LeftButton,pos=window.table.visualRect(index).center())
    assert window.bulk_checked[2]
    checkbox=window.games_model.index(row,GamesTableModel.C_CHECK)
    QTest.mouseClick(window.table.viewport(),Qt.MouseButton.LeftButton,pos=window.table.visualRect(checkbox).center())
    assert not window.bulk_checked[2]
    called=[]
    monkeypatch.setattr(window.cover_host,'show_info',lambda game:called.append(window.bulk_mode))
    window.show_game_info(window.games[0])
    assert called==[False] and window.bulk_checked=={}


def test_metadata_preserved_and_name_search_are_separate(window,monkeypatch):
    game=window.games[1]
    game.internal_name='DISC ORIGINAL';game.disc='2/2';game.vga='0';game.version='V1.003';game.date='20010201';game.artwork_serials=['T1234']
    workspace=ProductionWorkspace(window.cover_host,game,auto_search=False)
    workspace.gallery.query.setText('Different search')
    assert game.name=='Missing' and game.internal_name=='DISC ORIGINAL'
    monkeypatch.setattr(legacy,'update_game_state',lambda *args:None)
    workspace.rename()
    assert game.name=='Different search' and game.save_status=='pendiente_guardar'
    assert (game.disc,game.vga,game.version,game.date,game.artwork_serials)==('2/2','0','V1.003','20010201',['T1234'])
    workspace.reject()


@pytest.mark.parametrize('size',[(1280,780),(1024,720),(900,620)])
def test_gallery_six_whole_images_and_reachable_buttons(window,size):
    store=window.cover_host.store;game=window.games[1];view=store.view(game);session=store.session(view)
    for i in range(8):
        candidate=Candidate('test',f'Variant {i}',90,local_path=f'fixture-{i}',region=('JP','US','EU')[i%3])
        key=store.add_candidate(view,candidate,Image.new('RGB',(512+i,500+i),(180+i*5,70,20)))
        session.results.append(key)
    ws=ProductionWorkspace(window.cover_host,game,auto_search=False);ws.resize(*size);ws.show();QTest.qWait(60)
    assert len(ws.gallery.cards)==6 and ws.gallery.next.isEnabled()
    for position,card in enumerate(ws.gallery.cards):
        button_bottom=card.choose.mapTo(card,card.choose.rect().bottomRight())
        assert button_bottom.y()<card.height()
        assert all(not card.geometry().intersects(previous.geometry()) for previous in ws.gallery.cards[:position])
        assert card.image.pm.width()>=512
    last=ws.gallery.cards[-1]
    ws.gallery.scroll.ensureWidgetVisible(last.choose);QApplication.processEvents()
    p=last.choose.mapTo(ws.gallery.scroll.viewport(),last.choose.rect().bottomRight())
    assert p.y()<ws.gallery.scroll.viewport().height()
    ws.gallery.page(1);assert len(ws.gallery.cards)==2
    ws.reject()


def test_drafts_do_not_touch_sd_and_viewer_uses_original_normalizer(window):
    from openmenu_gdemu_manager.core.image_quality import normalize_cover
    from openmenu_gdemu_manager.ui.image_qt import pil_to_pixmap
    before=list(window.root_path.rglob('*'));game=window.games[1];store=window.cover_host.store;view=store.view(game)
    image=Image.new('RGB',(512,510),'red');candidate=Candidate('local','Red',95,local_path='generated')
    key=store.add_candidate(view,candidate,image)
    assert store.choose(view,key)=='chosen' and window.has_pending_changes()
    assert list(window.root_path.rglob('*'))==before and not game.selected_image
    ws=ProductionWorkspace(window.cover_host,game,auto_search=False)
    actual=ws.normalized_pixmap(key).toImage();expected=pil_to_pixmap(normalize_cover(image),(256,256)).toImage()
    assert actual==expected
    ws.inspect(key);viewer=ws.stack.currentWidget();viewer.set_mode(True)
    assert viewer.views[0].item.pixmap().toImage()==expected
    ws.reject()


def test_viewer_actual_size_is_one_image_pixel_per_screen_pixel(window,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import covers
    # Windows display scaling: 100 % must not stretch the cover by the scale factor.
    monkeypatch.setattr(covers.ImageView,'pixel_ratio',lambda self:2.5)
    game=window.games[1];store=window.cover_host.store;view=store.view(game)
    key=store.add_candidate(view,Candidate('local','Red',95,local_path='generated'),Image.new('RGB',(512,512),'red'))
    ws=ProductionWorkspace(window.cover_host,game,auto_search=False)
    ws.resize(1000,760);ws.show();ws.inspect(key);QTest.qWait(20)
    viewer=ws.stack.currentWidget();image=viewer.views[0]
    viewer.set_zoom(100)
    assert image.transform().m11()==pytest.approx(1/2.5) and round(image.effective_percent())==100
    assert viewer.zoom_label.text()=='100 %'
    viewer.set_zoom('fit');fitted=image.effective_percent()
    assert image.transform().m11()!=pytest.approx(1/2.5)
    assert viewer.zoom_label.text()==catalog.tr('full_view_percent',percent=round(fitted))
    viewer.step_zoom(1)
    assert viewer.zoom!='fit' and viewer.zoom>fitted and viewer.zoom%covers.ZOOM_STEP==0
    viewer.set_zoom('fit');viewer.step_zoom(-1)
    assert viewer.zoom!='fit' and viewer.zoom<fitted
    viewer.set_zoom(covers.ZOOM_MAX);viewer.step_zoom(1);assert viewer.zoom==covers.ZOOM_MAX
    viewer.set_zoom(covers.ZOOM_MIN);viewer.step_zoom(-1);assert viewer.zoom==covers.ZOOM_MIN
    ws.reject()


def test_readonly_blocks_mutations_and_stale_search_ignored(window):
    game=window.games[1];store=window.cover_host.store;view=store.view(game);window.write_allowed=False
    key=store.add_candidate(view,Candidate('test','Test',90),Image.new('RGB',(512,512),'red'))
    assert store.choose(view,key)=='blocked'
    assert not store.rename(view,'Changed') and game.name=='Missing'
    ws=ProductionWorkspace(window.cover_host,game,auto_search=False)
    ws.reject();ws.search_finished({'items':[(Candidate('test','Late',95),Image.new('RGB',(512,512)), '')],'query':'late'},ws.search_request)
    assert not store.session(view).results


def test_import_selection_invalid_blocked_duplicate_unchecked(window):
    dialog=ImportGamesDialog(window.settings,window.games,window)
    records=[(RomLibraryEntry('Covered','CDI','covered.cdi'),''),(RomLibraryEntry('New','GDI','new'),''),(RomLibraryEntry('Broken','GDI','broken'),'missing track')]
    dialog.received(records)
    assert dialog.checked==[False,True,False]
    assert not dialog.table.cellWidget(2,0).isEnabled()
    dialog.select_all();assert dialog.checked==[True,True,False]
    emitted=[];dialog.selected.connect(emitted.extend);dialog.accept_selection()
    assert [item.name for item in emitted]==['Covered','New']


@pytest.mark.parametrize('language',['en','es'])
def test_import_feedback_formats_actual_detected_and_selected_counts(window,language):
    set_language(language)
    dialog=ImportGamesDialog(window.settings,window.games,window)
    dialog.received([(RomLibraryEntry('New','CDI','new.cdi'),''),(RomLibraryEntry('Covered','CDI','covered.cdi'),'')])
    assert '{' not in dialog.feedback.text()
    assert dialog.feedback.text()==catalog.tr('detected_games',count=2,selected=1)
    dialog.toggle(0,False)
    assert dialog.feedback.text()==catalog.tr('detected_games',count=2,selected=0)
    dialog.reject();set_language('es')


@pytest.mark.parametrize('language',['en','es'])
def test_import_filter_hides_rows_without_changing_selection(window,language):
    set_language(language)
    dialog=ImportGamesDialog(window.settings,window.games,window)
    dialog.received([(RomLibraryEntry('Shenmue (PAL) [Disc 1]','CDI',r'G:\roms\Shenmue (PAL) [Disc 1]\disc.cdi'),''),
                     (RomLibraryEntry('Sonic Adventure','GDI',r'G:\roms\Sonic Adventure\disc.gdi'),''),
                     (RomLibraryEntry('Shenmue II','CDI',r'G:\roms\Shenmue II\disc.cdi'),'missing track')])
    before=list(dialog.checked);assert before==[True,True,False]
    dialog.filter.setText('  SHENMUE cdi ')
    assert [dialog.table.isRowHidden(row) for row in range(3)]==[False,True,False]
    assert dialog.checked==before and dialog.prepare.isEnabled()
    assert '{' not in dialog.feedback.text()
    assert dialog.feedback.text()==catalog.tr('detected_games_filtered',visible=2,count=3,selected=2)
    # The library folder shared by every game is not searched.
    dialog.filter.setText('roms');assert dialog.visible_rows()==[]
    dialog.filter.setText('sonic');dialog.row_clicked(1,1)
    assert dialog.checked==[True,False,False]
    dialog.filter.clear()
    assert dialog.visible_rows()==[0,1,2]
    assert dialog.feedback.text()==catalog.tr('detected_games',count=3,selected=1)
    # A game hidden by the filter stays selected and is still added.
    dialog.filter.setText('sonic')
    emitted=[];dialog.selected.connect(emitted.extend);dialog.accept_selection()
    assert [item.name for item in emitted]==['Shenmue (PAL) [Disc 1]']
    set_language('es')


@pytest.mark.parametrize('language',['en','es'])
def test_import_all_acts_on_visible_games_while_filtering(window,language):
    set_language(language)
    dialog=ImportGamesDialog(window.settings,window.games,window)
    dialog.received([(RomLibraryEntry('Hydro Thunder','CDI',r'G:\roms\Hydro Thunder\disc.cdi'),''),
                     (RomLibraryEntry('4 Wheel Thunder','CDI',r'G:\roms\4 Wheel Thunder\disc.cdi'),''),
                     (RomLibraryEntry('Sonic Adventure','GDI',r'G:\roms\Sonic Adventure\disc.gdi'),''),
                     (RomLibraryEntry('Thunder Force','GDI',r'G:\roms\Thunder Force\disc.gdi'),'missing track')])
    assert dialog.all.text()==catalog.tr('all') and dialog.checked==[True,True,True,False]
    dialog.filter.setText('thunder')
    # Sonic stays checked out of sight, and the checkbox says so.
    assert dialog.all.text()==catalog.tr('all_visible_hidden',count=3,hidden=1) and '{' not in dialog.all.text()
    assert dialog.all.checkState()==Qt.CheckState.Checked
    dialog.select_all()
    # Only the visible, valid games change; the hidden selection survives.
    assert dialog.checked==[False,False,True,False] and dialog.all.checkState()==Qt.CheckState.Unchecked
    assert dialog.feedback.text()==catalog.tr('detected_games_filtered',visible=3,count=4,selected=1)
    dialog.toggle(0,True);assert dialog.all.checkState()==Qt.CheckState.PartiallyChecked
    dialog.filter.clear()
    assert dialog.all.text()==catalog.tr('all')
    dialog.select_all();dialog.select_all();assert dialog.checked==[False,False,False,False]
    dialog.filter.setText('thunder');assert dialog.all.text()==catalog.tr('all_visible',count=3)
    dialog.select_all()
    emitted=[];dialog.selected.connect(emitted.extend);dialog.accept_selection()
    assert [entry.name for entry in emitted]==['Hydro Thunder','4 Wheel Thunder']
    set_language('es')


def test_import_reuses_inspected_games_until_their_files_change(monkeypatch,tmp_path):
    from openmenu_gdemu_manager.ui.v2 import import_games
    import_games.clear_inspection_cache()
    library=tmp_path/'library'
    for name in ('Alpha','Beta'):
        (library/name).mkdir(parents=True);(library/name/'disc.cdi').write_bytes(b'x')
    calls=[]
    def inspect(path,supported):
        calls.append(path.parent.name);return RomLibraryEntry(path.parent.name,'CDI',str(path))
    monkeypatch.setattr(import_games,'inspect_source',inspect)
    monkeypatch.setattr(import_games,'validate_source',lambda path:None)
    def run():
        worker=import_games.InspectWorker([library],{'CDI'});records=[]
        worker.finished.connect(records.extend);worker.run()
        return sorted(records,key=lambda record:record[0].name)
    first=run();assert sorted(calls)==['Alpha','Beta']
    first[0][0].existing_match=True
    second=run()
    # Picking the same folder again reads no image: only the listing is repeated.
    assert sorted(calls)==['Alpha','Beta'] and [r[0].name for r in second]==['Alpha','Beta']
    assert not second[0][0].existing_match and second[0][0].size_bytes==1
    (library/'Beta'/'disc.cdi').write_bytes(b'xy')
    (library/'Gamma').mkdir();(library/'Gamma'/'disc.cdi').write_bytes(b'z')
    third=run()
    assert sorted(calls)==['Alpha','Beta','Beta','Gamma'] and [r[0].size_bytes for r in third]==[1,2,1]
    import_games.clear_inspection_cache()


@pytest.mark.parametrize('language',['es','en'])
def test_import_shows_where_the_listed_games_come_from(window,monkeypatch,tmp_path,language):
    from openmenu_gdemu_manager.ui.v2 import import_games
    set_language(language)
    monkeypatch.setattr(import_games.InspectWorker,'run',lambda worker:worker.finished.emit([]))
    dialog=ImportGamesDialog(window.settings,window.games,window);dialog.resize(960,620);dialog.show()
    assert dialog.source_label.full_text==''
    first=tmp_path/'Sega - Dreamcast'/'Juegos';first.mkdir(parents=True)
    second=tmp_path/'Otra carpeta';second.mkdir()
    for folder in (first,first,second):
        dialog.inspect_paths([str(folder)])
        for _ in range(100):
            QTest.qWait(5)
            if dialog.scan_thread is None:break
    assert dialog.source_label.full_text==catalog.tr('source_chosen_many',path=str(first),count=1) and '{' not in dialog.source_label.full_text
    assert dialog.source_label.toolTip()==f'{first}\n{second}'
    # A long path is shortened in the middle and keeps both ends.
    dialog.source_label.resize(120,dialog.source_label.height());QTest.qWait(10)
    shown=dialog.source_label.text()
    assert '…' in shown and len(shown)<len(dialog.source_label.full_text) and shown.endswith(dialog.source_label.full_text[-3:])
    dialog.reject();set_language('es')


def test_import_folder_games_start_unchecked_and_hidden_checks_are_explained(window,monkeypatch,tmp_path):
    from openmenu_gdemu_manager.ui.v2 import import_games
    gb=1024**3
    monkeypatch.setattr(import_games,'free_space',lambda root:import_games.SPACE_MARGIN_BYTES+3*gb)
    library=tmp_path/'library';library.mkdir();game_file=tmp_path/'Single.cdi';game_file.write_bytes(b'x')
    records={'folder':[(RomLibraryEntry(n,'CDI',f'{n}.cdi',size_bytes=2*gb),'') for n in ('Hydro Thunder','Sonic Adventure','Shenmue')],
             'files':[(RomLibraryEntry('Single','CDI',str(game_file),size_bytes=gb),'')]}
    def run(worker):worker.finished.emit(records['files' if Path(worker.paths[0]).is_file() else 'folder'])
    monkeypatch.setattr(import_games.InspectWorker,'run',run)
    dialog=ImportGamesDialog(window.settings,window.games,window)
    def inspect(path):
        dialog.inspect_paths([str(path)])
        for _ in range(100):
            QTest.qWait(5)
            if dialog.scan_thread is None:break
    inspect(library)
    # A folder is a catalogue: nothing is checked until the user picks games.
    assert dialog.checked==[False,False,False] and not dialog.prepare.isEnabled()
    inspect(game_file)
    assert dialog.checked==[False,False,False,True] and dialog.prepare.isEnabled()
    dialog.filter.clear();dialog.select_all();dialog.filter.setText('hydro')
    text=dialog.capacity.text()
    assert catalog.tr('selection_hidden',count=3) in text and '{' not in text
    # The checkbox says why the total is larger than what is visible.
    assert dialog.all.text()==catalog.tr('all_visible_hidden',count=1,hidden=3) and '{' not in dialog.all.text()
    assert dialog.prepare.isEnabled()
    dialog.reject()


def test_import_folder_picker_starts_in_the_last_folder(window,monkeypatch,tmp_path):
    from openmenu_gdemu_manager.ui.v2 import import_games
    monkeypatch.setattr(import_games,'_last_folder','')
    asked=[]
    def picker(parent,caption,start=''):
        asked.append(start);return str(tmp_path)
    monkeypatch.setattr(import_games.QFileDialog,'getExistingDirectory',picker)
    dialog=ImportGamesDialog(window.settings,window.games,window)
    monkeypatch.setattr(dialog,'inspect_paths',lambda paths:None)
    dialog.pick_folder();dialog.reject()
    dialog=ImportGamesDialog(window.settings,window.games,window)
    monkeypatch.setattr(dialog,'inspect_paths',lambda paths:None)
    dialog.pick_folder();dialog.reject()
    assert asked==['',str(tmp_path)]


def test_import_explains_a_selection_that_does_not_fit_when_preparing(window,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import import_games
    gb=1024**3
    monkeypatch.setattr(import_games,'free_space',lambda root:4*gb)
    warnings=[];monkeypatch.setattr(import_games,'warn',lambda parent,title,text:warnings.append((title,text)))
    dialog=ImportGamesDialog(window.settings,window.games,window)
    assert dialog.free_slots==995 and dialog.free_bytes==4*gb and dialog.capacity.isHidden()
    dialog.received([(RomLibraryEntry('A','CDI','a.cdi',size_bytes=2*gb),''),(RomLibraryEntry('B','CDI','b.cdi',size_bytes=2*gb),''),(RomLibraryEntry('C','CDI','c.cdi',size_bytes=gb),'')])
    # Margin: one cover per checked game plus room to rebuild menu 01.
    assert dialog.margin_bytes()==3*import_games.COVER_BYTES_PER_GAME+import_games.SPACE_MARGIN_BYTES
    margin=import_games.format_bytes(dialog.margin_bytes());missing=import_games.format_bytes(dialog.needed_bytes()-4*gb)
    five,four=import_games.format_bytes(5*gb),import_games.format_bytes(4*gb)
    assert five=='5.0 GB'
    text=dialog.capacity.text()
    assert catalog.tr('selection_capacity',size=five,margin=margin,free=four,drive=str(window.root_path)) in text
    assert catalog.tr('selection_too_big',missing=missing) in text and '{' not in text
    # Prepare stays enabled and explains itself instead of doing nothing.
    assert dialog.prepare.isEnabled()
    emitted=[];dialog.selected.connect(emitted.extend);dialog.accept_selection()
    assert not emitted and len(warnings)==1
    title,details=warnings[0]
    assert title==catalog.tr('capacity_title')
    for line in (catalog.tr('capacity_games',count=3,size=five),catalog.tr('capacity_margin',size=margin),
                 catalog.tr('capacity_needed',size=import_games.format_bytes(dialog.needed_bytes())),
                 catalog.tr('capacity_free',drive=str(window.root_path),size=four),catalog.tr('capacity_missing',size=missing)):
        assert line in details
    assert '{' not in details
    dialog.toggle(0,False)
    assert dialog.capacity_problem()=='' and catalog.tr('selection_too_big',missing=missing) not in dialog.capacity.text()
    dialog.accept_selection();assert [e.name for e in emitted]==['B','C'] and len(warnings)==1


def test_import_explains_more_games_than_free_folders(window,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import import_games
    monkeypatch.setattr(import_games,'free_space',lambda root:10*1024**4)
    warnings=[];monkeypatch.setattr(import_games,'warn',lambda parent,title,text:warnings.append(text))
    # Folders 02..999: the old 127 cap had no documented hardware reason.
    assert import_games.MAX_USER_SLOT==999
    games=[GameItem(slot,f'G{slot}') for slot in range(2,998)]
    dialog=ImportGamesDialog(window.settings,games,window)
    assert dialog.free_slots==2
    dialog.received([(RomLibraryEntry(name,'CDI',f'{name}.cdi',size_bytes=1),'') for name in ('A','B','C')])
    expected=catalog.tr('selection_too_many',count=3,games=998,last=999,slots=2)
    assert dialog.prepare.isEnabled() and expected in dialog.capacity.text() and '{' not in expected
    dialog.accept_selection();assert expected in warnings[0]
    dialog.toggle(2,False);assert dialog.capacity_problem()==''
    dialog.reject()


def test_pending_save_button_keeps_readable_primary_colors(window):
    from openmenu_gdemu_manager.ui.v2 import design
    window.games[1].pending_add=True;window.games[1].save_status='pendiente_guardar'
    window.apply_filters();window._update_save_button_state();window._refresh_controls();QTest.qWait(20)
    button=window.save_changes_button
    assert button.property('role')=='primary' and button.property('attention')=='true'
    # The legacy attention marker must not replace the orange fill under white text.
    image=button.grab().toImage();sample=image.pixelColor(image.width()-8,image.height()//2)
    accent=design.QColor(design.colors()['accent'])
    assert max(abs(sample.red()-accent.red()),abs(sample.green()-accent.green()),abs(sample.blue()-accent.blue()))<24


def test_pending_save_button_breathes_and_counts_changes(window,monkeypatch):
    from PySide6.QtCore import QAbstractAnimation
    from PySide6.QtWidgets import QGraphicsDropShadowEffect
    from openmenu_gdemu_manager.ui.v2 import main_window as v2
    monkeypatch.setattr(v2,'_animations_enabled',lambda:True)
    window.games[1].pending_add=True;window.games[1].save_status='pendiente_guardar'
    window.apply_filters();window._update_save_button_state()
    button=window.save_changes_button
    assert button.text()==catalog.tr('save_count',count=1)
    assert isinstance(button.graphicsEffect(),QGraphicsDropShadowEffect)
    assert window._breath.state()==QAbstractAnimation.State.Running and not window.save_attention_timer.isActive()
    window._breathe(1.0);effect=button.graphicsEffect()
    assert effect.blurRadius()==36 and effect.color().name()==design_accent()
    window.games[1].pending_add=False;window.games[1].save_status=''
    window.apply_filters();window._update_save_button_state()
    assert button.graphicsEffect() is None and window._breath.state()!=QAbstractAnimation.State.Running
    # With Windows animations off the halo stays, without motion.
    monkeypatch.setattr(v2,'_animations_enabled',lambda:False)
    window.games[1].pending_add=True;window.games[1].save_status='pendiente_guardar'
    window.apply_filters();window._update_save_button_state()
    assert isinstance(button.graphicsEffect(),QGraphicsDropShadowEffect) and window._breath.state()!=QAbstractAnimation.State.Running


def test_missing_cover_filter_reads_as_a_checkbox_with_its_count(window,tmp_path):
    from openmenu_gdemu_manager.ui.v2.design import SelectionCheck
    window._refresh_controls()
    box=window.missing_button
    assert isinstance(box,SelectionCheck) and box.text()==catalog.tr('missing_only',count=2) and '{' not in box.text()
    assert box.isEnabled() and not box.isChecked() and [g.slot for g in window.filtered_games]==[2,3,4]
    box.setChecked(True);window.toggle_missing()
    assert [g.slot for g in window.filtered_games]==[3,4]
    # With every cover present there is nothing to filter, but an active filter can still be turned off.
    for game in window.games[1:]:game.has_placeholder_cover=False;game.current_cover=tmp_path/'cover.png'
    window._refresh_controls()
    assert box.text()==catalog.tr('missing_only',count=0) and box.isEnabled()
    box.setChecked(False);window.toggle_missing()
    assert not box.isEnabled() and [g.slot for g in window.filtered_games]==[2,3,4]


def test_bulk_proposal_is_previewed_in_the_collection_even_for_new_games(window):
    from PySide6.QtGui import QImage,QPainter
    from PySide6.QtWidgets import QStyleOptionViewItem
    window.games[1].pending_add=True
    candidate=Candidate('test','Proposal',99)
    window.bulk_proposals={3:BulkProposal(3,candidate,Image.new('RGB',(512,512),(0,0,255)),status='seleccionada'),
                           4:BulkProposal(4,candidate,None,status='omitida')}
    window.apply_filters()
    model=window.games_model;rows={g.slot:i for i,g in enumerate(model._games)}
    status=lambda slot:model.data(model.index(rows[slot],model.C_STATUS))
    assert catalog.tr('new_pending') in status(3) and catalog.tr('proposal') in status(3)
    assert catalog.tr('proposal') not in status(4)
    # The proposal itself is drawn in the cover cell; a skipped one is not.
    def cover_center(slot):
        image=QImage(96,96,QImage.Format.Format_RGB32);image.fill(0xffffff);painter=QPainter(image)
        option=QStyleOptionViewItem();option.rect=image.rect()
        window.table.itemDelegate().paint(painter,option,model.index(rows[slot],model.C_COVER));painter.end()
        return image.pixelColor(48,48)
    assert cover_center(3).blue()>200 and cover_center(3).red()<60
    assert cover_center(4).blue()<200 or cover_center(4).red()>60


def design_accent():
    from openmenu_gdemu_manager.ui.v2 import design
    return design.QColor(design.colors()['accent']).name()


def test_successful_save_with_deletion_rescans_without_asking_and_forgets_deleted_game(window,monkeypatch):
    scans=[]
    monkeypatch.setattr(legacy.MainWindow,'start_scan',lambda self:scans.append([g.slot for g in self.games]))
    monkeypatch.setattr(QMessageBox,'information',lambda *args,**kwargs:None)
    def asked(*args,**kwargs):raise AssertionError('asked to discard after a successful save')
    monkeypatch.setattr(QMessageBox,'question',asked)
    window.path_edit.setText(str(window.root_path))
    deleted=window.games[1];deleted.pending_delete=True;deleted.save_status='pendiente_eliminar'
    window.save_finished('ok')
    assert scans==[[2,4]] and deleted not in window.games and 3 not in window.games_by_slot
    assert not window.has_pending_changes()


def test_import_cannot_accept_or_enable_prepare_while_inspection_runs(window,monkeypatch):
    import time
    from openmenu_gdemu_manager.ui.v2 import import_games
    dialog=ImportGamesDialog(window.settings,window.games,window)
    dialog.received([(RomLibraryEntry('Ready','CDI','ready.cdi'),'')])
    def slow(worker):
        time.sleep(.15);worker.finished.emit([])
    monkeypatch.setattr(import_games.InspectWorker,'run',slow)
    emitted=[];dialog.selected.connect(emitted.extend)
    dialog.inspect_paths(['unused'])
    dialog.toggle(0,True);dialog.accept_selection()
    assert not emitted and not dialog.prepare.isEnabled() and not dialog.table.isEnabled()
    assert dialog.scan_thread in window.cover_jobs
    # A slow (mechanical) disk shows the spinning-disc loading screen over the list.
    assert not dialog.busy.isHidden() and dialog.busy.spinner.timer.isActive()
    for _ in range(100):
        QTest.qWait(10)
        if dialog.scan_thread is None:break
    assert dialog.scan_thread is None and dialog.prepare.isEnabled() and dialog.table.isEnabled()
    assert dialog.busy.isHidden() and not dialog.busy.spinner.timer.isActive()
    dialog.accept_selection();assert [entry.name for entry in emitted]==['Ready']


def test_import_inspection_reports_listing_then_each_game(window,monkeypatch,tmp_path):
    from openmenu_gdemu_manager.ui.v2 import import_games
    for name in ('Alpha','Beta'):
        (tmp_path/'library'/name).mkdir(parents=True)
        (tmp_path/'library'/name/'disc.cdi').write_bytes(b'x')
    monkeypatch.setattr(import_games,'inspect_source',lambda path,supported:RomLibraryEntry(path.parent.name,'CDI',str(path)))
    monkeypatch.setattr(import_games,'validate_source',lambda path:None)
    worker=import_games.InspectWorker([tmp_path/'library'],{'CDI'})
    steps=[];worker.progress.connect(lambda *step:steps.append(step))
    worker.run()
    assert steps==[(0,0,''),(1,2,'Alpha'),(2,2,'Beta')]
    worker=import_games.InspectWorker([tmp_path/'library'],{'CDI'});records=[]
    worker.finished.connect(records.extend);worker.run()
    assert [entry.size_bytes for entry,_ in records]==[1,1]
    dialog=ImportGamesDialog(window.settings,window.games,window)
    dialog.inspection_progress(0,0,'')
    assert dialog.busy.detail.text()==catalog.tr('source_listing')
    dialog.inspection_progress(3,40,'Shenmue (PAL) [Disc 1]')
    assert dialog.busy.detail.text()==catalog.tr('source_scanning_progress',current=3,total=40,name='Shenmue (PAL) [Disc 1]')
    dialog.reject()


def test_save_does_not_auto_accept_bulk_proposals(window,monkeypatch):
    candidate=Candidate('test','Proposal',99)
    window.bulk_proposals={3:BulkProposal(3,candidate,Image.new('RGB',(512,512)),status='seleccionada')}
    assert not window.has_pending_changes()
    called=[];monkeypatch.setattr(window,'save_bulk_proposals',lambda **kw:called.append('unexpected'))
    window.save_changes_to_sd(confirm=False)
    assert called==[] and not window.games[1].selected_image


@pytest.mark.parametrize('action',['discard','keep'])
def test_cancelled_cover_review_cannot_leave_hidden_selection(window,monkeypatch,action):
    import copy
    from PySide6.QtWidgets import QDialog
    from openmenu_gdemu_manager.ui.v2 import main_window as v2
    game=window.games[0];store=window.cover_host.store;view=store.view(game)
    key=store.add_candidate(view,Candidate('test','Blue',99),Image.new('RGB',(512,512),'blue'))
    store.choose(view,key)
    before=copy.deepcopy(game.__dict__);state=copy.deepcopy(window.state)
    persisted=[];workers=[]
    monkeypatch.setattr(window,'_persist_cover_selection',lambda *a,**kw:persisted.append(a))
    monkeypatch.setattr(v2.ConfirmApplyDialog,'exec',lambda self:QDialog.DialogCode.Rejected)
    window.save_changes_to_sd()
    assert not persisted and game.__dict__==before and window.state==state
    assert view.choice==key
    if action=='discard':store.discard(view)
    else:assert store.choose(view,view.cover)=='kept'
    assert not window.has_pending_changes()
    monkeypatch.setattr(legacy,'update_game_state',lambda *a:None)
    window.save_game_name(window.games[1],'Another name')
    monkeypatch.setattr(window,'start_busy',lambda *a:None)
    monkeypatch.setattr(window,'_start_worker',lambda worker,*a,**kw:workers.append(worker))
    window.save_changes_to_sd(confirm=False)
    assert not persisted and not game.selected_image and len(workers)==1


def test_cover_materialization_occurs_only_after_accepted_review(window,monkeypatch):
    from PySide6.QtWidgets import QDialog
    from openmenu_gdemu_manager.ui.v2 import main_window as v2
    store=window.cover_host.store;view=store.view(window.games[1]);events=[]
    key=store.add_candidate(view,Candidate('test','Blue',99),Image.new('RGB',(512,512),'blue'))
    store.choose(view,key)
    def review(dialog):
        assert not view.real.selected_image
        events.append('review');return QDialog.DialogCode.Accepted
    monkeypatch.setattr(v2.ConfirmApplyDialog,'exec',review)
    monkeypatch.setattr(window,'_persist_cover_selection',lambda *a,**kw:events.append('persist'))
    monkeypatch.setattr(window,'start_busy',lambda *a:None)
    monkeypatch.setattr(window,'_start_worker',lambda *a,**kw:events.append('worker'))
    assert window.save_changes_to_sd() is True
    assert events==['review','persist','worker']


def test_search_worker_delivers_on_gui_thread(window,monkeypatch):
    from openmenu_gdemu_manager.ui import workers
    monkeypatch.setattr(workers,'find_candidates',lambda *a,**kw:[])
    monkeypatch.setattr(workers,'load_saved_candidates',lambda *a:[])
    monkeypatch.setattr(workers,'append_search_event_for_game',lambda *a:None)
    ws=ProductionWorkspace(window.cover_host,window.games[1],auto_search=False)
    observed=[];original=ws.search_finished
    ws.search_finished=lambda payload,token:(observed.append(QThread.currentThread() is QApplication.instance().thread()),original(payload,token))
    ws.search()
    for _ in range(200):
        QTest.qWait(10)
        if ws.search_thread is None:break
    assert observed==[True] and ws.search_thread is None
    ws.reject()


def test_all_actions_have_resources_and_translations():
    for action,spec in catalog.ACTIONS.items():
        assert (catalog.REFERENCE/'icons'/f"{spec['icon']}.svg").is_file()
        for language in ('en','es'):assert 'v2.action.'+action in load_internal_language(language).strings
    for language in ('en','es'):
        assert 'slot_recovery.revert_in_progress' in load_internal_language(language).strings


def test_original_functions_remain_available(window):
    for name in ('force_backup_current_sd','open_provider_settings','export_reports','open_setup_wizard','check_for_updates','save_bulk_proposals','rebuild_templates_menu','rebuild_language_menu'):
        assert callable(getattr(window,name))


def test_discard_restores_name_state_without_deleting_history(window,monkeypatch):
    from openmenu_gdemu_manager.config import state
    monkeypatch.setattr(state,'flush_state',lambda *args:None)
    monkeypatch.setattr(legacy,'update_game_state',lambda *args:None)
    game=window.games[1];window.save_game_name(game,'Edited')
    window.discard_pending_changes()
    assert game.name=='Missing' and not window.has_pending_changes()


def test_discard_restores_bulk_cover_after_sd_save_failure(window,monkeypatch,tmp_path):
    from openmenu_gdemu_manager.core.image_quality import analyze_image
    from openmenu_gdemu_manager.config import state
    monkeypatch.setattr(state,'flush_state',lambda *a:None)
    monkeypatch.setattr(legacy,'update_game_state',lambda *a:None)
    monkeypatch.setattr(legacy,'export_reports',lambda *a:None)
    monkeypatch.setattr(window,'show_error',lambda *a:None)
    game=window.games[1]
    window.apply_after_bulk_save=False
    path=tmp_path/'bulk.png';Image.new('RGB',(512,512),'blue').save(path)
    result={'slot':game.slot,'status':'seleccionada','normalized':str(path),'original':str(path),'preview':str(path),'source':'test','score':99,'quality':analyze_image(Image.open(path))}
    window._finish_save_bulk([result]);window.save_error('synthetic save failure')
    assert game.selected_image and window.has_pending_changes()
    window.discard_pending_changes()
    assert not game.selected_image and game.has_placeholder_cover and not window.has_pending_changes()


def test_failed_slot_transaction_disables_v2_writes_until_recovery(window,monkeypatch):
    from openmenu_gdemu_manager.services.sd_slot_transaction import SdSlotTransactionService
    SdSlotTransactionService(window.root_path,'failed')._write_state('failed')
    monkeypatch.setattr(window,'show_error',lambda *a:None)
    window.save_error('failed transaction')
    assert not window.write_allowed and window.read_only_reason
    assert not window.add_game_button.isEnabled() and not window.save_changes_button.isEnabled()


def test_identical_cover_kept_and_tonal_variant_is_distinct(window):
    game=window.games[0];store=window.cover_host.store;view=store.view(game)
    same=store.add_candidate(view,Candidate('test','Same',90),Image.open(game.current_cover).convert('RGB'))
    assert store.choose(view,same)=='kept'
    other=store.add_candidate(view,Candidate('test','Other',90),Image.new('RGB',(512,510),(250,150,10)))
    assert store.choose(view,other)=='chosen'


def test_search_web_preserves_configured_templates(window,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import bridge
    monkeypatch.setattr(bridge,'web_search_templates',lambda _:[{'name':'Custom','url':'https://example.test/?q={raw_query}&id={product_id}'}])
    ws=ProductionWorkspace(window.cover_host,window.games[0],auto_search=False)
    ws.web_menu()
    assert ws.web_popup.actions()[0].text()=='Custom'
    ws.web_popup.close();ws.reject()


@pytest.mark.parametrize('ini,status,own_line',[(None,'missing',False),('open_time=1000\n','valid',False),('open_time=149\n','invalid',True)])
def test_collection_header_is_compact_and_gdemu_ini_needs_a_line_only_when_it_needs_attention(window,ini,status,own_line):
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    slot=window.root_path/'01';slot.mkdir()
    (slot/'track05.iso').write_bytes(b'[OPENMENU] openMenu NEODC_1')
    if ini:(window.root_path/'GDEMU.ini').write_text(ini)
    window.diagnostic=diagnose_storage(window.root_path);window._refresh_controls();QTest.qWait(20)
    assert window.diagnostic.configuration.status==status
    assert not hasattr(window,'heading') and not hasattr(window,'subtitle')
    assert window.configuration_note.isVisible()==own_line and window.configuration_details_button.isVisible()
    short=legacy_tr('v2.gdemu_config.short_'+status) if not own_line else None
    assert (short in window.destination.destination_subtitle) if short else 'GDEMU.ini' not in window.destination.destination_subtitle
    # The destination card is now the first thing in the window.
    assert window.destination.mapTo(window,window.destination.rect().topLeft()).y()<window.menuBar().height()+40


def test_destination_uses_real_diagnostic_values(window):
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import StorageDiagnostic,RouteSummary
    summary=RouteSummary(window.root_path,filesystem='FAT32',free_bytes=24*1024**3)
    window.diagnostic=StorageDiagnostic(window.root_path,'gdemu_structure','ok','openmenu_compatible',True,True,summary=summary)
    window._refresh_controls()
    assert 'FAT32' in window.destination.destination_subtitle and '24.0' in window.destination.destination_subtitle
    assert '{' not in window.destination.destination_subtitle


def test_worker_rescan_waits_for_thread_cleanup(window,monkeypatch):
    running=[True];called=[]
    monkeypatch.setattr(window,'operation_running',lambda:running[0])
    monkeypatch.setattr(legacy.MainWindow,'start_scan',lambda self:called.append('scan'))
    window.start_scan();assert not called
    running[0]=False;window.refresh_after_worker()
    assert called==['scan'] and not window._rescan_after_worker


def test_old_icon_only_setting_cannot_clip_v2_labels(window):
    window.toggle_bulk_mode();QTest.qWait(30)
    for button in (window.add_game_button,window.save_changes_button,window.bulk_mode_button,window.bulk_button):
        assert not button.property('iconOnly')
        assert button.width()>=button.fontMetrics().horizontalAdvance(button.text())+button.iconSize().width()+12



def test_destination_picker_clears_config_and_permissions_before_scan(window, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QFileDialog
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    slot=window.root_path/'01';slot.mkdir()
    (slot/'track05.iso').write_bytes(b'[OPENMENU] openMenu NEODC_1')
    (window.root_path/'GDEMU.ini').write_text('open_time=149\n')
    window.diagnostic=diagnose_storage(window.root_path)
    window._refresh_controls()
    assert window.configuration_note.isVisible()
    destination=tmp_path/'another-sd';destination.mkdir()
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:str(destination))
    captured=[]
    monkeypatch.setattr(window,'start_scan',lambda:captured.append((window.root_path,window.write_allowed,window.diagnostic,list(window.games),window.configuration_note.isVisible())))
    window.pick_root()
    assert captured==[(destination,False,None,[],False)]
    assert window.games_by_slot=={}


def test_destination_picker_cancel_keeps_config_and_context(window, monkeypatch):
    from PySide6.QtWidgets import QFileDialog
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    slot=window.root_path/'01';slot.mkdir()
    (slot/'track05.iso').write_bytes(b'[OPENMENU] openMenu NEODC_1')
    window.diagnostic=diagnose_storage(window.root_path)
    window._refresh_controls()
    before=(window.root_path,window.diagnostic,list(window.games),window.write_allowed,window.configuration_note.text())
    monkeypatch.setattr(QFileDialog,'getExistingDirectory',lambda *args:'')
    window.pick_root()
    assert before==(window.root_path,window.diagnostic,window.games,window.write_allowed,window.configuration_note.text())


def test_explicit_startup_root_does_not_discover_physical_storage(window, monkeypatch, tmp_path):
    monkeypatch.setattr(legacy,'recommended_initial_storage_path',lambda *a:pytest.fail('Physical storage probed'))
    app=QApplication.instance() or QApplication([])
    w=MainWindowV2(initial_root=tmp_path)
    assert w.root_path==tmp_path
    w.close();w.deleteLater();app.processEvents()



@pytest.mark.parametrize('language',['es','en'])
def test_collection_configuration_action_opens_real_readonly_details(window, monkeypatch, language):
    from PySide6.QtWidgets import QDialog, QLabel, QPushButton
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    set_language(language)
    slot=window.root_path/'01';slot.mkdir()
    (slot/'track05.iso').write_bytes(b'[OPENMENU] openMenu NEODC_1')
    path=window.root_path/'GDEMU.ini';path.write_text('open_time=149\n')
    window.diagnostic=diagnose_storage(window.root_path)
    window._refresh_controls();window.toggle_bulk_mode()
    assert window.configuration_details_button.isVisible()
    calls=[]
    def review(dialog):
        dialog.show();QApplication.instance().processEvents()
        assert 'GDEMU.ini' in ' '.join(w.text() for w in dialog.findChildren(QLabel))
        assert '150' in ' '.join(w.text() for w in dialog.findChildren(QLabel))
        for button in dialog.findChildren(QPushButton):
            assert button.isEnabled() and button.isVisible() and button.text() in ('Close','Cerrar')
        assert not window.bulk_mode
        target=__import__('os').environ.get('OPENMENU_V2_CAPTURE_DIR')
        if target:
            dialog.grab().save(str(Path(target)/f'collection-config-{language}.png'))
        calls.append(dialog.windowTitle());dialog.reject()
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(QDialog,'exec',review)
    QTest.mouseClick(window.configuration_details_button,Qt.MouseButton.LeftButton)
    assert len(calls)==1 and path.read_text()=='open_time=149\n'
    assert window.write_allowed



@pytest.mark.parametrize('language',['es','en'])
def test_empty_installed_collection_does_not_say_menu_is_missing(window, language):
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    set_language(language)
    slot=window.root_path/'01';slot.mkdir()
    (slot/'track05.iso').write_bytes(b'[OPENMENU] openMenu NEODC_1')
    window.diagnostic=diagnose_storage(window.root_path)
    window.games=[];window.games_by_slot={}
    window._refresh_controls()
    assert window.guidance.text()==catalog.tr('collection_empty')
    assert window.add_game_button.isEnabled()
    window.diagnostic=None;window.write_allowed=False
    window._refresh_controls()
    assert window.guidance.text()==catalog.tr('destination_unknown')


@pytest.mark.parametrize('language', ['en', 'es'])
@pytest.mark.parametrize('state', ['checked', 'invalid', 'unsupported'])
def test_cdi_import_uses_real_validation_and_clear_status(window, tmp_path, monkeypatch, language, state):
    from cdi_fixtures import classic_cdi
    from openmenu_gdemu_manager.ui.v2 import import_games
    set_language(language)
    image = classic_cdi(tmp_path/'generated.cdi', payload_cut=2048 if state == 'invalid' else 0)
    if state == 'unsupported':
        payload = bytearray(image.read_bytes()); payload[-8:-4] = b'\x09\x00\x00\x80'; image.write_bytes(payload)
    monkeypatch.setattr(import_games, 'inspect_source', lambda path, supported: RomLibraryEntry('Synthetic CDI', 'CDI', str(path)))
    records = []; errors = []
    worker = import_games.InspectWorker([image], {'CDI'})
    worker.finished.connect(records.extend); worker.error.connect(errors.append); worker.run()
    assert not errors and len(records) == 1
    dialog = ImportGamesDialog(window.settings, window.games, window); dialog.received(records)
    dialog.show(); QApplication.instance().processEvents()
    check = dialog.table.cellWidget(0, 0)
    if state == 'checked':
        assert check.isEnabled() and check.isChecked()
        assert dialog.table.item(0, 4).text() == catalog.tr('source_cdi_checked')
        assert dialog.table.item(0, 4).toolTip() == catalog.tr('source_cdi_scope')
        assert dialog.prepare.isEnabled()
    else:
        assert not check.isEnabled() and not check.isChecked() and not dialog.prepare.isEnabled()
        reason = dialog.table.item(0, 4).toolTip()
        assert ('requiere revisión' if language == 'es' else 'needs review') in reason if state == 'unsupported' else ('inválido' if language == 'es' else 'Invalid') in reason
    import os
    capture = os.environ.get('OPENMENU_V2_CAPTURE_DIR')
    if capture:
        folder = Path(capture); folder.mkdir(parents=True, exist_ok=True)
        dialog.grab().save(str(folder/f'cdi-import-{language}-{state}.png'))
    from PySide6.QtWidgets import QLabel
    assert any(label.text() == catalog.tr('prepare_real_hint') for label in dialog.findChildren(QLabel))
    header = dialog.table.horizontalHeader()
    assert header.fontMetrics().horizontalAdvance(catalog.tr('format')) + 20 <= header.sectionSize(3)
    before = image.read_bytes()
    dialog.reject(); dialog.deleteLater(); QApplication.instance().processEvents()
    assert image.read_bytes() == before
    set_language('es')


def test_setup_legacy_action_hands_off_to_original_update_review(window, monkeypatch):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialog
    from openmenu_gdemu_manager.ui.v2 import setup
    from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
    (window.root_path/'01').mkdir()
    (window.root_path/'01/track05.iso').write_bytes(b'unknown synthetic menu')
    diagnostic=diagnose_storage(window.root_path)
    assert diagnostic.legacy_menu_migratable and not diagnostic.write_allowed
    events=[]
    monkeypatch.setattr(window,'_can_abandon',lambda:True)
    monkeypatch.setattr(window,'operation_running',lambda:False)
    monkeypatch.setattr(window,'_has_registered_backup',lambda _:False)
    monkeypatch.setattr(window,'open_backup_prompt',lambda *args,**kwargs:events.append('backup') or True)
    class UpgradeReview:
        def __init__(self,*args):events.append('upgrade')
        def exec(self):return QDialog.DialogCode.Rejected
    monkeypatch.setattr(legacy,'LegacyMenuUpgradeDialog',UpgradeReview)
    monkeypatch.setattr(window,'start_scan',lambda:window.finish_diagnostic(diagnose_storage(window.root_path)))
    original_exec=setup.SetupWizardV2.exec
    def reviewed_exec(dialog):
        assert dialog.phase=='legacy_upgrade_required'
        assert dialog.use_button.text()==catalog.tr('setup_upgrade_action')
        QTimer.singleShot(0,dialog.use_button.click)
        return original_exec(dialog)
    monkeypatch.setattr(setup.SetupWizardV2,'exec',reviewed_exec)
    before=(window.root_path/'01/track05.iso').read_bytes()
    window.open_setup_wizard(diagnostic)
    assert events==['backup','upgrade']
    assert not window.write_allowed and window.games==[]
    assert (window.root_path/'01/track05.iso').read_bytes()==before
