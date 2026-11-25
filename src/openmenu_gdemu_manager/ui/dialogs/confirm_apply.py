from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ...i18n import tr, tr_count
from ..icons import vendor_qicon

PLATE = 52
GLYPH = 30
SAFETY_GLYPH = 16


class ConfirmApplyDialog(QDialog):
    """Last confirmation before writing to the SD.

    ``covers`` counts every cover the save writes; ``new_game_covers`` is the
    part of it that belongs to games being copied. Those covers are shown with
    the new games, not again as cover changes, so no change is counted twice.
    """

    def __init__(
        self,
        root_path: Path,
        covers: int,
        additions: int,
        deletions: int,
        parent=None,
        *,
        slot_moves: int = 0,
        product_updates: int = 0,
        new_game_covers: int = 0,
    ):
        super().__init__(parent)
        self.setWindowTitle(tr("dialog.confirm_apply.title"))
        self.setModal(True)
        self.resize(760, 430)
        self.root_path = Path(root_path)
        self.covers = covers
        self.additions = additions
        self.deletions = deletions
        self.slot_moves = slot_moves
        self.product_updates = product_updates
        self.new_game_covers = max(0, min(new_game_covers, covers, additions))
        self.tiles: dict[str, QWidget] = {}
        self._build_ui()

    @property
    def cover_changes(self) -> int:
        """Covers written for games already on the SD."""
        return self.covers - self.new_game_covers

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hero = QWidget()
        hero.setObjectName("SecurityCard")
        hero_row = QHBoxLayout(hero)
        hero_row.setContentsMargins(16, 14, 16, 14)
        hero_row.setSpacing(14)
        hero_row.addWidget(_plate("device-sd-card", "warning"), 0, Qt.AlignmentFlag.AlignTop)
        text = QVBoxLayout()
        text.setSpacing(4)
        title = QLabel(self._title_text())
        title.setObjectName("StatusTitle")
        message = QLabel(self._message_text())
        message.setObjectName("StatusMessage")
        message.setTextFormat(Qt.TextFormat.RichText)
        message.setWordWrap(True)
        text.addWidget(title)
        text.addWidget(message)
        hero_row.addLayout(text, 1)
        self.message_label = message
        layout.addWidget(hero)

        grid = QGridLayout()
        grid.setSpacing(10)
        additions_detail = (
            tr_count("dialog.confirm_apply.additions_covers", self.new_game_covers)
            if self.new_game_covers
            else ""
        )
        tiles = (
            ("covers", tr("dialog.confirm_apply.covers"), self.cover_changes, "photo", "success", ""),
            ("additions", tr("dialog.confirm_apply.additions"), self.additions, "device-gamepad-2", "accent", additions_detail),
            ("deletions", tr("dialog.confirm_apply.deletions"), self.deletions, "trash", "danger", ""),
            ("slot_moves", tr("dialog.confirm_apply.slot_moves"), self.slot_moves, "arrows-sort", "warning", ""),
            ("product_updates", tr("dialog.confirm_apply.product_updates"), self.product_updates, "barcode", "accent", ""),
        )
        for index, (key, label, value, icon_name, tone, detail) in enumerate(tiles):
            tone = tone if value else "zero"
            tile = self._tile(label, str(value), icon_name, tone, detail)
            self.tiles[key] = tile
            grid.addWidget(tile, index // 3, index % 3)
        rebuild = self._tile(
            tr("dialog.confirm_apply.rebuild_label"),
            tr("dialog.confirm_apply.rebuild_value"),
            "refresh",
            "neutral",
            "",
            textual=True,
        )
        self.tiles["rebuild"] = rebuild
        grid.addWidget(rebuild, 1, 2)
        for column in range(3):
            grid.setColumnStretch(column, 1)
        layout.addLayout(grid)

        if self._is_large_operation():
            note = QLabel(tr("dialog.confirm_apply.large_note"))
            note.setObjectName("ChipWarning")
            note.setWordWrap(True)
            layout.addWidget(note)
            self.note_label = note
        else:
            safety = QWidget()
            safety.setObjectName("ApplySafety")
            row = QHBoxLayout(safety)
            row.setContentsMargins(2, 0, 2, 0)
            row.setSpacing(8)
            lock = QLabel()
            lock.setObjectName("ApplySafetyIcon")
            lock.setFixedSize(SAFETY_GLYPH, SAFETY_GLYPH)
            lock.setPixmap(vendor_qicon("tabler", "lock", "muted", SAFETY_GLYPH).pixmap(QSize(SAFETY_GLYPH, SAFETY_GLYPH)))
            row.addWidget(lock, 0, Qt.AlignmentFlag.AlignTop)
            note = QLabel(self._note_text())
            note.setObjectName("ApplySafetyText")
            note.setWordWrap(True)
            row.addWidget(note, 1)
            layout.addWidget(safety)
            self.note_label = note

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = _dialog_button(tr("action.cancel"), "x", "default")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(cancel)
        apply = _dialog_button(self._apply_button_text(), "circle-check", "success")
        apply.clicked.connect(self.accept)
        buttons.addWidget(apply)
        layout.addLayout(buttons)
        # Writing to the SD must be a deliberate click: Enter cancels.
        apply.setAutoDefault(False)
        cancel.setDefault(True)
        cancel.setFocus()
        self.cancel_button = cancel
        self.apply_button = apply

    def _title_text(self) -> str:
        if self.slot_moves or self.product_updates:
            return tr("dialog.confirm_apply.repair_title")
        if self.covers and not self.additions and not self.deletions:
            return tr("dialog.confirm_apply.covers_title")
        return tr("dialog.confirm_apply.apply_title")

    def _message_text(self) -> str:
        root = f"<b>{self.root_path}</b>"
        actions: list[str] = [tr("dialog.confirm_apply.action_rebuild")]
        if self.slot_moves:
            actions.append(tr_count("dialog.confirm_apply.action_compact", self.slot_moves))
        if self.product_updates:
            actions.append(tr_count("dialog.confirm_apply.action_product", self.product_updates))
        if self.cover_changes:
            actions.append(tr_count("dialog.confirm_apply.action_covers", self.cover_changes))
        if self.additions:
            actions.append(tr_count("dialog.confirm_apply.action_add", self.additions))
        if self.deletions:
            actions.append(tr_count("dialog.confirm_apply.action_delete", self.deletions))
        return tr("dialog.confirm_apply.message", root=root, actions=", ".join(actions))

    def _note_text(self) -> str:
        if self._is_large_operation():
            return tr("dialog.confirm_apply.large_note")
        if self.slot_moves or self.deletions or self.additions:
            return tr("dialog.confirm_apply.slot_note")
        return tr("dialog.confirm_apply.cover_note")

    def _apply_button_text(self) -> str:
        if self.slot_moves or self.product_updates:
            return tr("dialog.confirm_apply.repair_button")
        if self.covers and not self.additions and not self.deletions:
            return tr("dialog.confirm_apply.covers_button")
        return tr("dialog.confirm_apply.apply_button")

    def _is_large_operation(self) -> bool:
        return self.slot_moves > 10 or self.deletions > 5

    def _tile(self, title: str, value: str, icon_name: str, tone: str, detail: str, textual: bool = False) -> QWidget:
        card = QWidget()
        card.setObjectName("DiagnosticTile")
        card.setProperty("plate", tone)
        row = QHBoxLayout(card)
        row.setContentsMargins(12, 12, 14, 12)
        row.setSpacing(12)
        row.addWidget(_plate(icon_name, tone), 0, Qt.AlignmentFlag.AlignVCenter)
        col = QVBoxLayout()
        col.setSpacing(0)
        col.addStretch(1)
        label = QLabel(title)
        label.setObjectName("TileTitle")
        label.setWordWrap(True)
        count = QLabel(value)
        count.setObjectName("ApplyValue" if textual else "ApplyCount")
        count.setProperty("zero", tone == "zero")
        font = count.font()
        # Tabular figures keep every count the same width in every tile.
        font.setFeature(QFont.Tag("tnum"), 1)
        count.setFont(font)
        col.addWidget(label)
        col.addWidget(count)
        if detail:
            note = QLabel(detail)
            note.setObjectName("ApplyDetail")
            col.addWidget(note)
            card.detail_label = note
        col.addStretch(1)
        row.addLayout(col, 1)
        card.title_label = label
        card.value_label = count
        accessible = tr("dialog.confirm_apply.tile_accessible", label=title, value=value)
        if detail:
            accessible = f"{accessible}. {detail}"
        card.setAccessibleName(accessible)
        return card


def _plate(icon_name: str, tone: str) -> QLabel:
    """A glyph on a soft square: the tone shows in the icon, not in a frame."""
    plate = QLabel()
    plate.setObjectName("ApplyPlate")
    plate.setProperty("plate", tone)
    plate.setFixedSize(PLATE, PLATE)
    plate.setAlignment(Qt.AlignmentFlag.AlignCenter)
    variant = {"zero": "muted", "neutral": "default"}.get(tone, tone)
    plate.setPixmap(vendor_qicon("tabler", icon_name, variant, GLYPH).pixmap(QSize(GLYPH, GLYPH)))
    return plate


def _dialog_button(text: str, icon_name: str, variant: str) -> QPushButton:
    button = QPushButton(text)
    button.setIcon(vendor_qicon("tabler", icon_name, variant, 22))
    button.setIconSize(QSize(22, 22))
    button.setMinimumHeight(44)
    button.setMinimumWidth(150)
    button.setProperty("variant", variant)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button
