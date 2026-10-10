"""Illustrated native backup workflow over the original copy worker/service."""
import logging
import copy
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QTimer, QUrl, Qt, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QDialog, QVBoxLayout, QProgressBar, QScrollArea

from ...i18n import tr as app_tr
from ...config.settings import save_settings
from ...services.backup_service import set_backup_decision, BackupError
from ...services.sd_registry import write_backup_registry
from ...dreamcast.storage_diagnostics import diagnose_storage
from ..dialogs.backup_prompt import BackupPromptDialog
from .catalog import tr
from .design import Button, SelectionCheck, label
from .preparation import Header, PathStrip, StatusCard, Confirmation, scroll_body, footer

log = logging.getLogger(__name__)


class BackupPromptV2(BackupPromptDialog):
    """Keep source, worker, copy manifest and successful registry semantics."""
    def __init__(self, diagnostic, parent=None, force=False, allow_skip=True):
        self.phase = 'choose'
        self.failed = False
        self._successful_destination = None
        self._recording_warning = ''
        self.clock = QElapsedTimer()
        super().__init__(diagnostic,parent,force,allow_skip)
        self.setProperty('v2Dedicated',True)
        self.setMinimumSize(600,380)
        self.resize(800,520)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._elapsed)
        self._adapt_size()

    def _build_ui(self):
        root=QVBoxLayout(self)
        root.setContentsMargins(18,14,18,14)
        root.setSpacing(10)
        self.body_scroll,body=scroll_body(root)
        self.header=Header(tr('backup_heading'),tr('backup_intro' if self.allow_skip else 'backup_required_intro'),artwork=True)
        body.addWidget(self.header)
        self.source_strip=PathStrip(tr('backup_source'),str(self.diagnostic.root))
        body.addWidget(self.source_strip)
        self.target_strip=PathStrip(tr('backup_target'),str(self.destination),glyph='folder-open')
        self.destination_label=self.target_strip
        self.choose_button=Button('browse',self.choose_destination,text=app_tr('dialog.backup.choose'))
        self.target_strip.actions.addWidget(self.choose_button)
        body.addWidget(self.target_strip)
        self.advice=label(tr('backup_advice'),wrap=True)
        self.advice.setObjectName('ChipWarning')
        body.addWidget(self.advice)
        self.remember_check=SelectionCheck(tr('backup_remember'))
        self.remember_check.setVisible(self.allow_skip)
        body.addWidget(self.remember_check)
        self.preference_notice=label('',tone='warning',wrap=True)
        self.preference_notice.hide()
        body.addWidget(self.preference_notice)
        self.result_card=StatusCard()
        self.result_card.artwork.hide()
        self.result_card.hide()
        self.progress=QProgressBar()
        self.progress.setTextVisible(False)
        self.result_card.body.addWidget(self.progress)
        self.progress.hide()
        self.count_label=label('',title=True,wrap=True)
        self.result_card.body.addWidget(self.count_label)
        self.count_label.hide()
        self.elapsed_label=label('',muted=True)
        self.result_card.body.addWidget(self.elapsed_label)
        self.elapsed_label.hide()
        self.status=label('',wrap=True)
        self.status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_card.body.addWidget(self.status)
        self.scope=label(tr('backup_progress_scope'),muted=True,wrap=True)
        self.result_card.body.addWidget(self.scope)
        self.scope.hide()
        self.details_button=Button('info',self.toggle_details,text=tr('backup_details'),compact=True)
        self.details_button.setCheckable(True)
        self.result_card.body.addWidget(self.details_button,0,Qt.AlignmentFlag.AlignLeft)
        self.details_button.hide()
        self.details=label('',wrap=True)
        self.details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.details_scroll=QScrollArea()
        self.details_scroll.setWidgetResizable(True)
        self.details_scroll.setWidget(self.details)
        self.details_scroll.setFixedHeight(90)
        self.details_scroll.hide()
        self.result_card.body.addWidget(self.details_scroll)
        self.open_button=Button('browse',self.open_backup_folder,text=tr('backup_open'),compact=True)
        self.open_button.hide()
        self.result_card.body.addWidget(self.open_button,0,Qt.AlignmentFlag.AlignLeft)
        body.addWidget(self.result_card)
        row,self.branding=footer(root)
        self.cancel_button=Button('cancel',self.reject)
        row.addWidget(self.cancel_button)
        self.skip_button=Button('next',self.skip_backup,text=app_tr('dialog.backup.skip')) if self.allow_skip else None
        if self.skip_button:row.addWidget(self.skip_button)
        self.backup_button=Button('save',self.start_backup,text=app_tr('dialog.backup.now'),role='primary')
        row.addWidget(self.backup_button)
        self.continue_button=Button('select',self.accept,text=tr('backup_continue'))
        self.continue_button.hide()
        row.addWidget(self.continue_button)
        self.cancel_button.setDefault(True)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._adapt_size()

    def _adapt_size(self):
        if not hasattr(self,'header'):return
        self.header.artwork.setVisible(self.width()>=720 and self.height()>=500 and self.phase=='choose')
        self.branding.setVisible(self.width()>=720)

    def _confirm_message(self,text,accept_label=None):
        confirm=Confirmation(self,tr('backup_confirm_heading'),text,accept_label or app_tr('dialog.backup.now'))
        return confirm.exec()==QDialog.DialogCode.Accepted

    def start_backup(self):
        if self._backup_active or self.phase=='success':return
        self.failed=False
        self._recording_warning=''
        try:
            super().start_backup()
        except (OSError,BackupError) as exc:
            log.exception('Backup preparation failed')
            self._backup_active=False
            self._set_busy(False,'')
            self._show_failure(str(exc))

    def skip_backup(self):
        if self._backup_active or not self.allow_skip or self.phase=='success':return
        remembered=self.remember_check.isChecked()
        message=tr('backup_skip_body')+'\n\n'+tr('backup_skip_remembered' if remembered else 'backup_skip_once')
        confirm=Confirmation(self,tr('backup_skipping'),message,app_tr('dialog.backup.skip'))
        if confirm.exec()!=QDialog.DialogCode.Accepted:return
        if remembered:
            proposed=set_backup_decision(copy.deepcopy(self.settings),self.diagnostic,'skipped')
            try:
                save_settings(proposed)
            except OSError:
                log.exception('Could not save backup skip preference')
                self.preference_notice.setText(tr('backup_preferences_failed'))
                self.preference_notice.show()
                return
            self.settings=proposed
        self.accept()

    def _set_busy(self,busy,message):
        super()._set_busy(busy,message)
        self.remember_check.setEnabled(not busy)
        for strip in (self.source_strip,self.target_strip):strip.value.setEnabled(not busy)
        if busy:
            self.phase='preparing'
            self.result_card.set_tone('info')
            self.result_card.title.setText(tr('backup_prepare_title'))
            self.result_card.message.setText(tr('backup_prepare_body'))
            self.result_card.show()
            self.count_label.hide()
            self.status.setText(tr('backup_busy_note'))
            self.clock.start()
            self.timer.start()
            self.elapsed_label.show()
            self.scope.setText(tr('backup_progress_scope'))
            self.scope.hide()
            self.details_scroll.hide()
            self.details_button.hide()
            self.open_button.hide()
            self.advice.hide()
            self.header.intro.hide()
            self.backup_button.hide()
            if self.skip_button:self.skip_button.hide()
            self.remember_check.hide()
            self._elapsed()
        else:
            self.timer.stop()
        self._adapt_size()

    def _elapsed(self):
        if self.clock.isValid():
            seconds=self.clock.elapsed()//1000
            self.elapsed_label.setText(tr('backup_elapsed',time=f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'))

    @Slot(int,int,str)
    def backup_progress(self,current,total,file_name):
        super().backup_progress(current,total,file_name)
        self.phase='copying'
        self.result_card.title.setText(tr('backup_running_title'))
        self.result_card.message.setText(tr('backup_running_body'))
        self.count_label.setText(tr('backup_progress_counts',current=current,total=total))
        self.count_label.show()
        self.status.setText(tr('backup_current_file',file=file_name)+'\n'+tr('backup_busy_note'))
        self.scope.show()

    @Slot(str)
    def backup_finished(self,destination):
        # Copy/manifest completion is independent from optional source metadata.
        self._backup_result=destination
        proposed=set_backup_decision(copy.deepcopy(self.settings),self.diagnostic,'backed_up',Path(destination))
        try:
            save_settings(proposed)
            self.settings=proposed
        except OSError:
            log.exception('Completed backup preferences could not be saved')
            self._recording_warning=tr('backup_preferences_warning')
        # Never mutate a read-only/blocked source. Recheck before optional registry.
        current=diagnose_storage(self.diagnostic.root)
        if self.diagnostic.write_allowed and current.write_allowed:
            try:
                write_backup_registry(self.diagnostic.root,Path(destination))
            except OSError:
                log.exception('Completed backup source registry could not be saved')
                self._recording_warning=tr('backup_registry_warning')

    @Slot(str)
    def backup_error(self,message):
        log.error('Backup copy failed: %s',message)
        super().backup_error(message)

    @Slot()
    def _backup_stopped(self):
        # Keep wrappers alive through the entire finished signal emission.
        thread,worker=self.backup_thread,self.backup_worker
        self._backup_active=False
        self.backup_thread=None
        self.backup_worker=None
        self._set_busy(False,self.status.text())
        if self._backup_result is not None:
            self._successful_destination=Path(self._backup_result)
            self._backup_result=None
            self.phase='success'
            self.failed=False
            self.result_card.set_tone('success')
            self.result_card.title.setText(tr('backup_success_title'))
            self.result_card.message.setText(tr('backup_success_body'))
            self.status.setText(str(self._successful_destination))
            self.open_button.show()
            self.continue_button.show()
            self.progress.hide()
            self.scope.setText(self._recording_warning)
            self.scope.setVisible(bool(self._recording_warning))
            self.cancel_button.hide()
            self.choose_button.setEnabled(False)
            self.continue_button.setDefault(True)
        elif self._backup_failure is not None:
            message=self._backup_failure
            self._backup_failure=None
            self._show_failure(message)
        else:
            self.phase='choose'
            self.backup_button.show()
            if self.skip_button:self.skip_button.show()
        self._adapt_size()

    def _show_failure(self,message):
        self.phase='error'
        self.failed=True
        self.result_card.show()
        self.result_card.set_tone('danger')
        self.result_card.title.setText(tr('backup_error_title'))
        self.result_card.message.setText(tr('backup_error_body'))
        self.status.setText(tr('backup_error_partial'))
        if message=='El respaldo no puede quedar dentro de la SD/origen.':
            message=tr('backup_error_inside')
        elif message.startswith('La ruta origen no existe o no es carpeta: '):
            message=tr('backup_error_source',path=str(self.diagnostic.root))
        self.details.setText(message)
        self.details_button.show()
        self.details_button.setChecked(False)
        self.details_button.setText(tr('backup_details'))
        self.details_scroll.hide()
        self.progress.hide()
        self.count_label.hide()
        self.scope.hide()
        self.backup_button.action='scan'
        self.backup_button.setText(tr('backup_retry'))
        self.backup_button.refresh_icon()
        self.backup_button.show()
        if self.skip_button:self.skip_button.show()
        self.remember_check.setVisible(self.allow_skip)
        self._adapt_size()

    def toggle_details(self):
        opened=self.details_button.isChecked()
        self.details_scroll.setVisible(opened)
        self.details_button.setText(tr('backup_details_hide' if opened else 'backup_details'))

    def open_backup_folder(self):
        if self._successful_destination:
            if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._successful_destination))):
                self.status.setText(tr('backup_open_error'))

    def accept(self):
        if not self._backup_active:
            super().accept()
