"""Read-only «Datos del juego» / «Datos de la imagen» cards over original data.

Values are interpreted for reading (region names, VGA yes/no, readable dates);
the original GameItem/Candidate fields are never rewritten here.
"""
from pathlib import Path

from PySide6.QtCore import QDate, QLocale, QSize, Qt, QUrl
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from ...core.models import VALID_STATES
from ...i18n import active_language, tr as app_tr, translate_status
from ...services.cover_library import load_saved_candidates
from ..image_qt import pil_to_pixmap
from . import catalog
from .catalog import tr, variant
from .design import Button, TextLabel, colors, icon, label

COVER_SIZE = 76
WIDTH = 680
HEIGHT_RANGE = (420, 720)
# Smallest height on a short screen: header, one section and the footer.
MIN_HEIGHT = 260

# Dreamcast IP.BIN region letters, plus the two-letter forms used by providers.
_REGION_LETTERS = (('J', 'region.jpn'), ('U', 'region.usa'), ('E', 'region.eur'))
_REGION_WORDS = {'JP': 'J', 'JPN': 'J', 'JAP': 'J', 'US': 'U', 'USA': 'U', 'EU': 'E', 'EUR': 'E', 'PAL': 'E', 'P': 'E'}


def region_text(code):
    """Readable region names; empty when the code is not a known region."""
    raw = (code or '').strip().upper()
    letters = _REGION_WORDS.get(raw, raw.replace('P', 'E'))
    if not letters or set(letters) - {'J', 'U', 'E', ' ', '-'}:
        return ''
    return ' · '.join(app_tr(key) for letter, key in _REGION_LETTERS if letter in letters)


def date_text(value):
    raw = (value or '').strip()
    if not raw.strip('0'):
        return tr('no_date')
    date = QDate.fromString(raw, 'yyyyMMdd')
    if not date.isValid():
        return tr('no_date') if raw.isdigit() else raw
    return QLocale(active_language()).toString(date, tr('date_pattern'))


def vga_text(value):
    raw = (value or '').strip()
    return {'1': tr('yes'), '0': tr('no')}.get(raw, raw)


def disc_text(value):
    number, _, total = (value or '').strip().partition('/')
    if number.isdigit() and total.isdigit():
        return tr('disc_of', number=int(number), total=int(total))
    return (value or '').strip()


class ElidedLabel(TextLabel):
    """Single-line path with the middle elided and the full text as tooltip."""

    def __init__(self, text):
        super().__init__(text)
        self.full_text = text
        self.setToolTip(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

    def sizeHint(self):
        return QSize(min(super().sizeHint().width(), 240), super().sizeHint().height())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        elided = self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle, max(1, self.width()))
        if elided != self.text():
            super().setText(elided)


def cover_thumbnail(pixmap, chosen=False):
    thumb = QLabel()
    thumb.setObjectName('InfoCover')
    thumb.setProperty('chosen', chosen)
    thumb.setFixedSize(COVER_SIZE, COVER_SIZE)
    thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
    if pixmap is not None and not pixmap.isNull():
        thumb.setPixmap(pixmap)
    else:
        thumb.setPixmap(icon('photo', colors()['muted'], 28).pixmap(28, 28))
        thumb.setAccessibleName(tr('no_cover'))
    return thumb


def chip(text, tone=None, tooltip=''):
    item = label(text)
    item.setObjectName('InfoChip')
    if tone:
        item.setProperty('tone', tone)
    if tooltip:
        item.setToolTip(tooltip)
    item.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
    return item


class Section(QFrame):
    """Titled card with a column grid of small label + normal value."""

    def __init__(self, key, columns=3):
        super().__init__()
        self.setObjectName('InfoSection')
        self.key = key
        self.COLUMNS = columns
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 12)
        layout.setSpacing(8)
        layout.addWidget(label(tr(key), title=True))
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(18)
        self.grid.setVerticalSpacing(10)
        for column in range(self.COLUMNS):
            self.grid.setColumnStretch(column, 1)
        layout.addLayout(self.grid)
        self.row = self.column = 0
        self.values = {}

    def add(self, key, value, *, span=1, widget=None, elide=False):
        if self.column + span > self.COLUMNS:
            self.row, self.column = self.row + 1, 0
        cell = QWidget()
        box = QVBoxLayout(cell)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(2)
        caption = label(tr(key), muted=True)
        box.addWidget(caption)
        if widget is None:
            missing = not value
            widget = ElidedLabel(value) if elide and value else label(value or tr('unavailable'), wrap=True)
            if missing:
                widget.setProperty('tone', 'missing')
            elif not elide:
                widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        widget.setObjectName('InfoValue')
        widget.setAccessibleName(tr(key))
        box.addWidget(widget)
        self.grid.addWidget(cell, self.row, self.column, 1, span, Qt.AlignmentFlag.AlignTop)
        self.values[key] = widget
        self.column += span
        return widget


class InfoDialog(QDialog):
    """Header (cover, name, chips), optional warnings, sections and footer."""

    def __init__(self, parent, title):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(WIDTH, HEIGHT_RANGE[0])
        self.sections = {}
        self.chips = []
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        content = QWidget()
        # Surface keeps the theme background instead of Fusion's grey.
        content.setObjectName('Surface')
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(12)
        self.scroll.setWidget(content)
        root.addWidget(self.scroll, 1)
        self.footer = QHBoxLayout()
        self.footer.setSpacing(8)
        root.addLayout(self.footer)

    def header(self, pixmap, name, chips, chosen=False):
        row = QHBoxLayout()
        row.setSpacing(14)
        row.addWidget(cover_thumbnail(pixmap, chosen), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(8)
        self.name = label(name, heading=True, wrap=True)
        self.name.setObjectName('InfoName')
        text.addWidget(self.name)
        line = QHBoxLayout()
        line.setSpacing(6)
        for item in chips:
            self.chips.append(item)
            line.addWidget(item)
        line.addStretch()
        text.addLayout(line)
        text.addStretch()
        row.addLayout(text, 1)
        self.body.addLayout(row)

    def section(self, key, columns=3):
        section = Section(key, columns)
        self.sections[key] = section
        self.body.addWidget(section)
        return section

    def finish(self, left=(), right=()):
        self.body.addStretch()
        for widget in left:
            self.footer.addWidget(widget)
        self.footer.addStretch()
        for widget in right:
            self.footer.addWidget(widget)
        close = Button('close', self.reject)
        close.setDefault(True)
        self.footer.addWidget(close)
        self.close_button = close
        self.resize(WIDTH, self.fitting_height())

    def natural_height(self):
        """Height that shows all content without scrolling, ignoring the screen."""
        margins = self.layout().contentsMargins()
        footer = self.footer.sizeHint().height()
        content = self.scroll.widget().layout().heightForWidth(WIDTH - margins.left() - margins.right() - 4)
        if content < 0:
            content = self.scroll.widget().sizeHint().height()
        height = content + footer + self.layout().spacing() + margins.top() + margins.bottom() + 2
        return max(HEIGHT_RANGE[0], min(height, HEIGHT_RANGE[1]))

    def fitting_height(self):
        """Natural height, kept inside the screen; scrolling is only a fallback
        for screens shorter than the content."""
        screen = (self.parentWidget() or self).screen()
        available = screen.availableGeometry().height() - 60 if screen else 0
        height = self.natural_height()
        return min(height, max(MIN_HEIGHT, available)) if available > 0 else height


def _pixmap(store, key, size):
    if not key:
        return None
    try:
        image = store.image(key)
    except (OSError, ValueError, KeyError):
        return None
    screen = QGuiApplication.primaryScreen()
    ratio = max(2.0, screen.devicePixelRatio() if screen else 1.0)
    pixmap = pil_to_pixmap(image, (int(size * ratio), int(size * ratio)))
    pixmap.setDevicePixelRatio(ratio)
    return pixmap


def game_info_dialog(host, game, parent=None):
    """Card for one game; actions call the original window/store services."""
    real, store, window = game.real, host.store, host.window
    dialog = InfoDialog(parent or window, catalog.action_label('info'))
    region = region_text(real.region)
    chips = [chip(tr('position_chip', slot=f'{real.slot:03d}'))]
    raw_region = (real.region or '').strip()
    chips.append(chip(region or (raw_region or app_tr('region.unknown')),
                      tooltip=tr('region_code', code=raw_region) if raw_region else ''))
    renamed = game.title != game.original
    if real.pending_add:chips.append(chip(tr('new_pending'), 'success'))
    if real.pending_delete:chips.append(chip(tr('remove_pending'), 'danger'))
    if renamed:chips.append(chip(tr('name_pending'), 'success'))
    if game.choice:chips.append(chip(tr('cover_pending_chip'), 'success'))
    if real.save_status == 'pendiente_guardar' and not (renamed or game.choice or real.pending_add):
        chips.append(chip(tr('changes_pending_chip'), 'success'))
    dialog.header(_pixmap(store, game.choice or game.cover, COVER_SIZE), game.title, chips, chosen=bool(game.choice))
    for code in real.consistency_warnings:
        warning = label(app_tr('scan_repair.warning.' + code), wrap=True)
        warning.setObjectName('ChipWarning')
        dialog.body.addWidget(warning)

    openmenu = dialog.section('section_openmenu', 4)
    openmenu.add('openmenu_name', game.title, span=1 if renamed else 2)
    if renamed:openmenu.add('saved_name', game.original)
    status = QComboBox()
    for key in sorted(VALID_STATES):status.addItem(translate_status(key), key)
    status.setCurrentIndex(max(0, status.findData(real.status)))
    status.setEnabled(store.writable)
    status.currentIndexChanged.connect(lambda: window.set_status(real, status.currentData()))
    openmenu.add('cover_status', '', widget=status)
    openmenu.add('quality', real.quality_label or tr('not_analyzed'))

    disc = dialog.section('section_disc', 4)
    product = (real.product_id or '').strip()
    slot_reference = product.startswith('SLOT')
    disc_id = disc.add('disc_id', '' if slot_reference else product)
    disc.add('internal_name', real.internal_name, span=2)
    disc.add('disc', disc_text(real.disc))
    disc.add('version', (real.version or '').strip())
    disc.add('date', date_text(real.date), span=1 if slot_reference else 2)
    disc.add('vga', vga_text(real.vga))
    if slot_reference:
        # SLOT names the menu position, never the disc: say so on both values.
        reference = disc.add('technical_reference', product)
        for widget in (disc_id, reference):widget.setToolTip(tr('not_disc_id'))

    folder = str(real.folder) if real.folder else ''
    if folder or real.source_path or real.media_type:
        # A new game has no SD folder yet: only its chosen source is shown.
        files = dialog.section('section_files', 4)
        if folder:files.add('folder_on_sd', folder, span=3, elide=True)
        if real.source_path and real.source_path != folder:
            files.add('source_path', real.source_path, span=3, elide=True)
        files.add('format', real.media_type)

    history = load_saved_candidates(real)
    if history:
        saved = dialog.section('history_real')
        row = QHBoxLayout()
        row.setSpacing(6)
        for candidate in history:
            key = store.add_candidate(game, candidate)
            row.addWidget(Button('inspect', lambda _, k=key: (dialog.accept(), window.inspect_image(real, k, parent)), text=candidate.title, compact=True))
        row.addStretch()
        saved.layout().addLayout(row)

    remove = Button('remove', lambda: (dialog.accept(), window.toggle_delete_game(real)),
                    text=tr('undo_remove') if real.pending_delete else None)
    remove.setEnabled(store.writable)
    right = []
    if renamed:
        undo = Button('undo_name', lambda: (store.rename(game, game.original), dialog.accept()))
        undo.setEnabled(store.writable)
        right.append(undo)
    open_folder = Button('browse', lambda: window.open_path(real.folder), text=tr('open_folder'))
    open_folder.setVisible(bool(real.folder))
    right.append(open_folder)
    dialog.finish([remove], right)
    dialog.remove_button, dialog.folder_button, dialog.status_combo = remove, open_folder, status
    return dialog


def image_info_dialog(host, game, image_key, parent=None):
    """Same card structure for one candidate image."""
    store = host.store
    item = store.images[image_key]
    candidate = store.candidate_objects.get(image_key)
    dialog = InfoDialog(parent or host.window, catalog.action_label('image_info'))
    match = (tr('product_match') if candidate and candidate.product_match else tr('alias_match') if candidate and candidate.alias_match
             else tr('edition_warning') if item.get('weak_match') else tr('local_match') if item.get('variant_index') else tr('match_sample'))
    raw_region = (item.get('region') or '').strip()
    chips = [chip(f"{item['width']} × {item['height']} px"),
             chip(region_text(raw_region) or raw_region or tr('unidentified'), tooltip=tr('region_code', code=raw_region) if raw_region else '')]
    dialog.header(_pixmap(store, image_key, COVER_SIZE), item['title'], chips)
    image = dialog.section('section_image')
    image.add('available_design', variant(item))
    image.add('quality', tr('cover_quality', label=item.get('quality_label', ''), score=item.get('quality_score', 0)))
    image.add('match', match)
    origin = dialog.section('section_origin')
    origin.add('provider', item.get('provider', ''))
    origin.add('available_file', item.get('sourceFile', ''), span=2, elide=True)
    origin.add('sources', ' · '.join(item.get('duplicate_sources', [])) or tr('unavailable'), span=3)
    origin.add('original_image', tr('original_note'), span=3)
    left = []
    if candidate:
        def open_source():
            url = candidate.source_url or candidate.url
            if url and QUrl(url).scheme() == 'https':QDesktopServices.openUrl(QUrl(url))
            elif candidate.local_path:host.window.open_path(Path(candidate.local_path).parent)
        left.append(Button('web', open_source, text=tr('open_source')))
    dialog.finish(left)
    return dialog
