"""Native, reusable presentation atoms for setup and backup; no storage logic."""
from PySide6.QtCore import QByteArray, Qt, QRectF, Slot, QSize
from PySide6.QtGui import QPainter, QColor
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QVBoxLayout, QWidget, QLineEdit, QScrollArea, QSizePolicy, QDialog

from . import design, catalog
from .design import Button, label, TextLabel
from .catalog import tr


class FlowTextLabel(TextLabel):
    """A scroll-contained label must reserve every wrapped line at its width."""
    def minimumSizeHint(self):
        hint=super().minimumSizeHint()
        height=self.heightForWidth(self.width()) if self.wordWrap() else hint.height()
        return QSize(hint.width(),max(hint.height(),height))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if self.wordWrap() and event.size().width()!=event.oldSize().width():
            self.updateGeometry()


class CardArtwork(QWidget):
    """Decorative vector art, independent from the outline command icon family."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('PreparationArtwork')
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(design.METRICS['preparation-art-width'], design.METRICS['preparation-art-height'])
        self.tone = 'accent'
        self.raw = (catalog.REFERENCE / 'artwork/dreamcast-sd.svg').read_bytes()

    def paintEvent(self, event):
        c = design.colors()
        tone = self.tone if self.tone in c else 'accent'
        raw = self.raw.replace(b'{{accent}}', c['accent'].encode()).replace(b'{{soft}}', c.get(tone+'_soft', c['soft']).encode())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        QSvgRenderer(QByteArray(raw)).render(p, QRectF(self.rect()))


class StateBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tone, self.glyph = 'info', 'info-circle'
        self.setFixedSize(design.METRICS['preparation-state-icon'], design.METRICS['preparation-state-icon'])
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def paintEvent(self, event):
        c = design.colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(c[self.tone]))
        p.drawEllipse(self.rect().adjusted(1,1,-1,-1))
        design.icon(self.glyph, c['paper'], 28).paint(p, (self.width()-28)//2, (self.height()-28)//2,28,28)


class DiagnosticPathEdit(QLineEdit):
    """Return validates this input without activating the dialog's primary."""
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.returnPressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class PathStrip(QFrame):
    def __init__(self, caption, value='', glyph='device-sd-card', editable=False):
        super().__init__()
        self.setObjectName('Card')
        grid = QGridLayout(self)
        grid.setContentsMargins(12,8,12,8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(0)
        badge = label('')
        badge.setPixmap(design.icon(glyph, design.colors()['accent'], 30).pixmap(30,30))
        badge.setFixedWidth(32)
        grid.addWidget(badge,0,0,2,1)
        self.caption = label(caption, muted=True)
        self.value = DiagnosticPathEdit(value) if editable else QLineEdit(value)
        self.value.setAccessibleName(caption)
        self.value.setReadOnly(not editable)
        if not editable:
            self.value.setObjectName('PreparationPath')
        self.value.setToolTip(value)
        self.value.setMinimumWidth(40)
        self.value.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Fixed)
        self.value.textChanged.connect(self.value.setToolTip)
        grid.addWidget(self.caption,0,1)
        grid.addWidget(self.value,1,1)
        holder = QWidget()
        self.actions = QHBoxLayout(holder)
        self.actions.setContentsMargins(0,0,0,0)
        self.actions.setSpacing(8)
        grid.addWidget(holder,0,2,2,1)
        grid.setColumnStretch(1,1)

    def setText(self, text):
        self.value.setText(text)
        self.value.setCursorPosition(0)

    def text(self):
        return self.value.text()


class StatusCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('Card')
        self.tone = 'info'
        row = QHBoxLayout(self)
        row.setContentsMargins(14,12,14,12)
        row.setSpacing(12)
        self.badge = StateBadge()
        row.addWidget(self.badge,0,Qt.AlignmentFlag.AlignTop)
        self.body = QVBoxLayout()
        self.body.setSpacing(6)
        self.title = label('', heading=True, wrap=True, label_type=FlowTextLabel)
        self.title.setProperty('preparationTitle',True)
        self.message = label('',wrap=True,label_type=FlowTextLabel)
        self.body.addWidget(self.title)
        self.body.addWidget(self.message)
        row.addLayout(self.body,1)
        self.artwork = CardArtwork()
        row.addWidget(self.artwork,0,Qt.AlignmentFlag.AlignVCenter)
        self.set_tone('info')

    def set_tone(self,tone):
        self.tone = tone
        c = design.colors()
        self.setStyleSheet(f'QFrame#Card {{background:{c[tone+"_soft"]};border:1px solid {c[tone]};border-radius:8px;}}')
        self.title.setProperty('tone',tone)
        self.badge.tone = tone
        self.badge.glyph = {'success':'check','danger':'x','warning':'alert-triangle','info':'info-circle'}[tone]
        self.badge.update()
        self.artwork.tone = tone
        self.artwork.update()
        design.repolish(self.title)


class Header(QWidget):
    def __init__(self, title, intro, artwork=False):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0,0,0,0)
        body = QVBoxLayout()
        body.setSpacing(6)
        heading = label(title,heading=True,wrap=True)
        heading.setProperty('preparationHeading',True)
        body.addWidget(heading)
        self.intro = label(intro,wrap=True)
        body.addWidget(self.intro)
        row.addLayout(body,1)
        self.artwork = CardArtwork() if artwork else None
        if self.artwork:
            self.artwork.setFixedHeight(110)
            row.addWidget(self.artwork)


class FocusScrollArea(QScrollArea):
    """All focusable children, including checkboxes, stay visible on Tab."""
    def __init__(self,parent=None):
        super().__init__(parent)
        from PySide6.QtWidgets import QApplication
        QApplication.instance().focusChanged.connect(self._ensure_focus)

    @Slot(QWidget,QWidget)
    def _ensure_focus(self,previous,current):
        if current and self.widget() and self.widget().isAncestorOf(current):
            self.ensureWidgetVisible(current)


def scroll_body(root):
    scroll = FocusScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    content = QWidget()
    content.setObjectName('Surface')
    body = QVBoxLayout(content)
    body.setContentsMargins(0,0,0,0)
    body.setSpacing(10)
    body.setAlignment(Qt.AlignmentFlag.AlignTop)
    scroll.setWidget(content)
    root.addWidget(scroll,1)
    return scroll, body


def footer(root):
    row = QHBoxLayout()
    row.setSpacing(8)
    branding = label(tr('brand_footer'),muted=True,tone='brand')
    branding.setObjectName('PreparationBrand')
    row.addWidget(branding)
    row.addStretch(1)
    root.addLayout(row)
    return row, branding


class Confirmation(QDialog):
    """Compact action-specific confirmation; safe return remains the default."""
    def __init__(self,parent,title,message,accept_text):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(400)
        self.resize(500,220)
        root=QVBoxLayout(self)
        root.setContentsMargins(20,18,20,16)
        card=StatusCard()
        card.artwork.hide()
        card.title.setText(title)
        card.message.setText(message)
        self.body_scroll,body=scroll_body(root)
        body.addWidget(card)
        row=QHBoxLayout()
        row.addStretch(1)
        self.back_button=Button('previous',self.reject,text=catalog.action_label('back'))
        self.back_button.setDefault(True)
        self.continue_button=Button('next',self.accept,text=accept_text,role='primary')
        row.addWidget(self.back_button)
        row.addWidget(self.continue_button)
        root.addLayout(row)
