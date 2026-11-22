"""Compact destination guidance over the original setup and backup services."""
from pathlib import Path
import copy
import logging

import shiboken6
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QDialog, QHBoxLayout, QLineEdit, QMessageBox, QProgressBar, QScrollArea, QVBoxLayout, QGridLayout

from ...config.settings import load_settings, save_settings
from ...services.backup_service import set_backup_decision, completed_backup_exists
from ...dreamcast.storage_diagnostics import diagnose_storage
from ...services.setup_service import install_openmenu_base, OpenMenuSetupError
from ...i18n import tr as app_tr
from ..dialogs.setup_wizard import SetupWizardDialog, _confirm_dialog, _setup_error_text, _diagnostic_tiles
from . import design, configuration
from .catalog import tr
from .design import Button, SelectionCheck, box, label, repolish
from .service_call import invoke_service
from .preparation import Header, PathStrip, StatusCard, Confirmation, scroll_body, footer


log=logging.getLogger(__name__)


class SetupWizardV2(SetupWizardDialog):
    """Retain decisions/services, replace presentation and stale-path handling."""

    def __init__(self, diagnostic=None, parent=None, force_backup_prompt=False):
        self._rendering = False
        self._backup_active = False
        self._installed = False
        self._install_active = False
        self._checking = False
        self.phase = "unselected"
        super().__init__(diagnostic, parent, force_backup_prompt)
        self.setMinimumSize(600,380)
        self.resize(800,560)
        self._adapt_size()
        if diagnostic is None:
            self._show_unselected()

    def _build_ui(self):
        root=QVBoxLayout(self)
        root.setContentsMargins(18,14,18,14)
        root.setSpacing(10)
        self.body_scroll,body=scroll_body(root)
        self.header=Header(tr('setup_heading'),tr('setup_intro'))
        body.addWidget(self.header)
        self.destination_strip=PathStrip(tr('destination_label'),str(self.selected_path or ''),editable=True)
        self.route_edit=self.destination_strip.value
        self.route_edit.setPlaceholderText(tr('setup_path_hint'))
        self.route_edit.setAccessibleName(tr('setup_path_hint'))
        self.pick_other_button=Button('browse',self.pick_route)
        self.refresh_button=Button('scan',self.run_diagnostic,text=tr('setup_validate'))
        self.destination_strip.actions.addWidget(self.pick_other_button)
        self.destination_strip.actions.addWidget(self.refresh_button)
        body.addWidget(self.destination_strip)
        self.route_edit.textEdited.connect(self._route_edited)
        self.route_edit.returnPressed.connect(self.run_diagnostic)
        self.security_card=StatusCard()
        self.security_title=self.security_card.title
        self.security_message=self.security_card.message
        self.security_icon=label('')  # Compatibility sink for the legacy controller.
        body.addWidget(self.security_card)
        self.scope=label(tr('setup_scope'),muted=True,wrap=True)
        self.security_card.body.addWidget(self.scope)
        self.configuration_note=label('',muted=True,wrap=True)
        self.security_card.body.addWidget(self.configuration_note)
        self.warning=label('',tone='warning',wrap=True)
        self.security_card.body.addWidget(self.warning)
        self.summary=label('',wrap=True)
        body.addWidget(self.summary)
        self.details_action=Button('info',self.toggle_details,text=app_tr('dialog.setup.show_details'),compact=True)
        self.details_action.setCheckable(True)
        self.security_card.body.addWidget(self.details_action,0,Qt.AlignmentFlag.AlignLeft)
        self.details=label('',wrap=True)
        self.details.setTextFormat(Qt.TextFormat.RichText)
        self.details_scroll=QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setFixedHeight(100)
        self.details_scroll.setWidget(self.details)
        self.details_scroll.hide()
        body.addWidget(self.details_scroll)
        self.backup_card,backup=box(margins=12,spacing=6,name='Card')
        top=QHBoxLayout()
        glyph=label('')
        glyph.setPixmap(design.icon('folder-open',design.colors()['warning'],32).pixmap(32,32))
        top.addWidget(glyph)
        text=QVBoxLayout()
        text.addWidget(label(tr('setup_backup_title'),title=True))
        text.addWidget(label(tr('setup_backup_body'),muted=True,wrap=True))
        top.addLayout(text,1)
        self.backup_button=Button('browse',self.backup_current_sd,text=app_tr('dialog.setup.backup_sd'))
        top.addWidget(self.backup_button)
        backup.addLayout(top)
        self.skip_backup_button=SelectionCheck(tr('backup_remember'))
        self.skip_backup_button.clicked.connect(self._reminder_changed)
        backup.addWidget(self.skip_backup_button)
        body.addWidget(self.backup_card)
        self.backup_progress_bar=QProgressBar()
        self.backup_progress_bar.hide()
        body.addWidget(self.backup_progress_bar)
        row,self.branding=footer(root)
        self.cancel_button=Button('cancel',self.reject)
        row.addWidget(self.cancel_button)
        self.use_button=Button('select',self.handle_primary_action,text=app_tr('dialog.setup.use_path'))
        self.use_button.hide()
        row.addWidget(self.use_button)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._adapt_size()

    def _adapt_size(self):
        if not hasattr(self,'security_card'):return
        self.security_card.artwork.setVisible(self.width()>=720 and self.height()>=500)
        self.branding.setVisible(self.width()>=720)

    def _reminder_changed(self,checked):
        if checked:self.skip_backup_for_current_sd()

    def skip_backup_for_current_sd(self):
        if not self.diagnostic or self._backup_active or self._checking or self._install_active:
            self.skip_backup_button.setChecked(False)
            return
        message=tr('backup_skip_body')+'\n\n'+tr('backup_skip_remembered')
        confirm=Confirmation(self,tr('backup_skipping'),message,app_tr('dialog.backup.confirm_skip_action'))
        if confirm.exec()!=QDialog.DialogCode.Accepted:
            self.skip_backup_button.setChecked(False)
            return
        proposed=set_backup_decision(copy.deepcopy(self.settings),self.diagnostic,'skipped')
        try:
            save_settings(proposed)
        except OSError:
            log.exception('Could not save backup reminder preference')
            self.skip_backup_button.setChecked(False)
            self.summary.setText(tr('backup_preferences_failed'))
            self.summary.show()
            return
        self.settings=proposed
        self.skip_backup_button.setChecked(False)
        self.backup_card.hide()
        self.backup_button.hide()
        self.skip_backup_button.hide()
        self.summary.setText(tr('setup_backup_ignored'))
        self.summary.show()

    def _working(self,value):
        for widget in (self.route_edit,self.pick_other_button,self.refresh_button,self.use_button,self.cancel_button,self.backup_button,self.skip_backup_button):
            widget.setEnabled(not value)

    def _show_unselected(self):
        self.phase='unselected'
        self.security_card.set_tone('info')
        self.backup_card.hide()
        self.security_title.setText(tr('setup_choose_title'))
        self.security_message.setText(tr('setup_choose_body'))
        self.warning.hide()
        self.summary.hide()
        self.configuration_note.hide()
        self.details_action.hide()
        self.details_scroll.hide()
        self.details_action.setChecked(False)
        self.use_button.hide()
        self.backup_button.hide()
        self.skip_backup_button.hide()
        self.refresh_button.setEnabled(bool(self.route_edit.text().strip()))
        self._browse_role('primary')

    def _browse_role(self, role):
        self.pick_other_button.setProperty('role', role)
        self.pick_other_button.refresh_icon()
        repolish(self.pick_other_button)

    def _route_edited(self, _text):
        if self._rendering or self._install_active or self._checking:
            return
        self.diagnostic = None
        self.selected_path = None
        self._installed = False
        self._show_unselected()

    def run_diagnostic(self):
        if self._backup_active or self._install_active or self._checking or not self.route_edit.text().strip():
            return
        self._installed=False
        self.phase='checking'
        self._checking=True
        self._working(True)
        self.security_card.set_tone('info')
        self.security_title.setText(tr('setup_checking_title'))
        self.security_message.setText(tr('setup_checking_body'))
        path=Path(self.route_edit.text().strip())
        try:
            self.diagnostic=invoke_service(lambda:diagnose_storage(path),self)
            self.selected_path=self.diagnostic.root
        finally:
            self._checking=False
            self._working(False)
        self._show_diagnostic(self.diagnostic)

    def _backup_registered(self, diagnostic):
        return super()._backup_registered(diagnostic) or completed_backup_exists(self.settings,diagnostic)

    def _show_diagnostic(self, diagnostic):
        self.summary.clear()
        self.summary.hide()
        self._rendering = True
        try:
            super()._show_diagnostic(diagnostic)
        finally:
            self._rendering = False
        self.route_edit.setCursorPosition(0)
        config = diagnostic.configuration
        self.configuration_note.setText(configuration.summary(config))
        self.configuration_note.setVisible(config is not None and config.status != 'valid')
        self.configuration_note.setProperty('tone', 'warning' if config and config.status in ('invalid', 'unreadable', 'review') else '')
        repolish(self.configuration_note)
        self.details.setText(self._diagnostic_rows + '<br>' + self.details.text() + '<br><br>' + configuration.details(config))
        # status cards use semantic properties, never legacy object-name variants.
        self.security_card.setObjectName('Card')
        self.security_message.setText(self.security_message.text().strip().replace('\n\n', '\n'))
        tone = 'success' if diagnostic.write_allowed else 'info' if diagnostic.prepare_allowed else 'warning' if diagnostic.scan_allowed else 'danger'
        self.security_title.setProperty('tone', tone)
        repolish(self.security_title)
        self.warning.setVisible(bool(self.warning.text()))
        self.summary.setVisible(bool(self.summary.text()))
        self.refresh_button.setEnabled(True)
        self._browse_role('secondary' if self.use_button.isVisibleTo(self) else 'primary')
        if diagnostic.prepare_allowed:
            self.use_button.action = 'install_template'
            self.use_button.setText(app_tr('dialog.setup.install_base'))
        else:
            self.use_button.action = 'select'
        if diagnostic.prepare_allowed:
            self.phase='empty'
            self.security_title.setText(tr('setup_empty_title'))
            self.security_message.setText(tr('setup_empty_body'))
        elif diagnostic.write_allowed:
            self.phase='ready'
        elif diagnostic.scan_allowed and diagnostic.legacy_menu_migratable:
            self.phase='legacy_upgrade_required'
            self.security_title.setText(tr('setup_upgrade_title'))
            self.security_message.setText(tr('setup_upgrade_body'))
            self.use_button.setText(tr('setup_upgrade_action'))
        elif diagnostic.scan_allowed:
            self.phase='readonly'
            self.security_title.setText(tr('setup_readonly_title'))
            self.security_message.setText(tr('setup_readonly_body'))
            self.use_button.setText(tr('setup_readonly_action'))
        else:
            self.phase='inaccessible' if diagnostic.storage_health=='not_accessible' else 'security_blocked'
            self.security_title.setText(tr('setup_inaccessible_title' if self.phase=='inaccessible' else 'setup_blocked_title'))
            if self.phase=='inaccessible':self.security_message.setText(tr('setup_inaccessible_body'))
        self.security_card.set_tone(tone)
        self.pick_other_button.setText(tr('setup_choose_other') if self.phase in ('inaccessible','security_blocked') else design.catalog.action_label('browse'))
        self.backup_card.setVisible(not self.backup_button.isHidden())
        self._adapt_size()
        self.use_button.refresh_icon()
        self.use_button.setDefault(bool(diagnostic.scan_allowed or diagnostic.prepare_allowed or diagnostic.write_allowed))

    def _update_tiles(self, diagnostic):
        # Accessible compact text in the technical disclosure. N/A is neutral.
        from html import escape
        rows = []
        for tile in _diagnostic_tiles(diagnostic):
            key = tile['id']
            title = app_tr('dialog.setup.tile.' + key)
            rows.append(f'<div><b>{escape(title)}:</b> {escape(tile["value"])}</div>')
        self._diagnostic_rows = ''.join(rows)

    def toggle_details(self):
        opened = self.details_action.isChecked()
        self.details_scroll.setVisible(opened)
        self.details_action.setText(app_tr('dialog.setup.hide_details' if opened else 'dialog.setup.show_details'))

    def handle_primary_action(self):
        if self._backup_active or self._install_active or self._checking:
            return
        if self._installed:
            self.accept_selection()
            return
        # Always diagnose the currently displayed path, even after programmatic edits.
        self.run_diagnostic()
        if self.diagnostic is None:
            return
        if self.diagnostic.prepare_allowed:
            self.prepare_openmenu_base()
        elif self.diagnostic.scan_allowed or self.diagnostic.write_allowed:
            self.accept_selection()

    def accept_selection(self):
        if self._backup_active or self._install_active or self._checking:
            return
        self.run_diagnostic()
        if self.diagnostic and (self.diagnostic.scan_allowed or self.diagnostic.write_allowed):
            self.selected_path = self.diagnostic.root
            QDialog.accept(self)

    def prepare_openmenu_base(self):
        if not self.diagnostic or not self.diagnostic.prepare_allowed or self._backup_active or self._install_active or self._checking:
            return
        if not _confirm_dialog(self, app_tr('dialog.setup.install_confirm'), app_tr('dialog.setup.install_action')):
            return
        # Services revalidate internally. Keep the outcome visible until Continue.
        self._install_active=True
        self.phase='install_running'
        self._working(True)
        self.security_card.set_tone('info')
        self.security_title.setText(tr('setup_installing_title'))
        self.security_message.setText(tr('setup_installing_body'))
        destination,settings=self.diagnostic.root,load_settings()
        try:
            result = invoke_service(lambda:install_openmenu_base(destination,settings),self)
        except (OpenMenuSetupError, OSError) as exc:
            QMessageBox.warning(self, self.windowTitle(), _setup_error_text(exc) if isinstance(exc, OpenMenuSetupError) else str(exc))
            self._install_active=False
            self._working(False)
            self.run_diagnostic()
            self.phase='install_failed'
            self.security_card.set_tone('danger')
            self.security_title.setText(tr('setup_install_failed'))
            return
        finally:
            self._install_active=False
            self._working(False)
        self.diagnostic = result
        self.selected_path = result.root
        self._show_diagnostic(result)
        self._installed = bool(result.scan_allowed and result.write_allowed and result.menu_state=='openmenu_compatible')
        if self._installed:
            self.phase='installed'
            self.security_card.set_tone('success')
            self.security_title.setText(tr('setup_installed_title'))
            self.security_message.setText(tr('setup_installed_body'))
            self.use_button.setText(tr('setup_continue'))
        else:
            self.phase='install_failed'
            self.security_card.set_tone('danger')
            self.security_title.setText(tr('setup_install_failed'))
            self.security_message.setText(tr('setup_install_incompatible'))

    def backup_current_sd(self):
        if self._backup_active or self._install_active or self._checking or not self.diagnostic:return
        from .backup import BackupPromptV2
        dialog=BackupPromptV2(self.diagnostic,self,force=True,allow_skip=False)
        self._backup_active=True
        try:
            dialog.exec()
        finally:
            self._backup_active=False
        self.settings=load_settings()
        self._show_diagnostic(self.diagnostic)
        if dialog.failed:
            self.summary.setText(tr('setup_backup_failed'))
            self.summary.show()

    def _backup_stopped(self):
        self._backup_active = False
        self.backup_thread = None
        self.backup_worker = None
        for widget in (self.route_edit, self.pick_other_button, self.refresh_button, self.skip_backup_button, self.cancel_button):
            widget.setEnabled(True)
        if self.diagnostic:
            self._show_diagnostic(self.diagnostic)

    def reject(self):
        if not (self._backup_active or self._install_active or self._checking):
            super().reject()

    def closeEvent(self, event):
        if self._backup_active or self._install_active or self._checking:
            event.ignore()
        else:
            super().closeEvent(event)
