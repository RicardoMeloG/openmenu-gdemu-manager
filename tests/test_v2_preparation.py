"""Real native setup/backup states, reachability and worker lifecycle."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QScrollArea, QCheckBox, QLineEdit, QWidget

from openmenu_gdemu_manager.i18n import set_language, active_language
from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
from openmenu_gdemu_manager.ui.v2 import design, setup
from openmenu_gdemu_manager.ui.v2.backup import BackupPromptV2
from openmenu_gdemu_manager.ui.v2.preparation import Confirmation
from openmenu_gdemu_manager.ui.dialogs import backup_prompt


@pytest.fixture
def app(monkeypatch):
    instance=QApplication.instance() or QApplication([])
    previous=active_language()
    previous_theme=design.theme
    set_language('es')
    design.apply_theme(instance)
    monkeypatch.setattr(backup_prompt,'save_settings',lambda *args:None)
    from openmenu_gdemu_manager.ui.v2 import backup
    monkeypatch.setattr(backup,'save_settings',lambda *args:None)
    monkeypatch.setattr(setup,'save_settings',lambda *args:None)
    yield instance
    set_language(previous)
    design.apply_theme(instance,previous_theme)


def show(app,dialog,size=(720,500)):
    dialog.resize(*size)
    dialog.show()
    app.processEvents()
    return dialog


def dispose(app,dialog):
    assert not getattr(dialog,'_backup_active',False)
    dialog.hide()
    dialog.deleteLater()
    app.processEvents()


def reachable(app,dialog):
    # Scroll-contained actions must be reachable through the actual scroll view.
    for button in dialog.findChildren(QWidget):
        if not isinstance(button,(QPushButton,QCheckBox,QLineEdit)) or not button.isVisibleTo(dialog):continue
        parent=button.parentWidget()
        while parent and parent is not dialog:
            if isinstance(parent,QScrollArea):
                parent.ensureWidgetVisible(button)
                app.processEvents()
            parent=parent.parentWidget()
        top=button.mapTo(dialog,button.rect().topLeft())
        bottom=button.mapTo(dialog,button.rect().bottomRight())
        assert dialog.rect().contains(top) and dialog.rect().contains(bottom),(button.text(),dialog.size(),top,bottom)
    if hasattr(dialog,'body_scroll'):
        dialog.body_scroll.verticalScrollBar().setValue(0)
        app.processEvents()


def capture(dialog,state,language='es',theme='light'):
    location=os.environ.get('OPENMENU_V2_CAPTURE_DIR')
    if not location:return
    folder=Path(location)
    folder.mkdir(parents=True,exist_ok=True)
    width,height=dialog.width(),dialog.height()
    disclosure='expanded' if getattr(dialog,'details_scroll',None) and dialog.details_scroll.isVisible() else 'collapsed'
    name=f'preparation-{state}-{language}-{theme}-{width}x{height}-{disclosure}'
    file=folder/(name+'.png')
    pixmap=dialog.grab()
    assert pixmap.save(str(file))
    root=Path(__file__).resolve().parents[1]
    record={'path':file.relative_to(root).as_posix(),'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
            'state':state,'languages':language,'themes':theme,'logical_sizes':[width,height],
            'qt_scales':os.environ.get('QT_SCALE_FACTOR','windows-system'),'dpr':pixmap.devicePixelRatio(),
            'disclosure':disclosure}
    (folder/(name+'.json')).write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')


@pytest.mark.parametrize('theme',['light','dark'])
@pytest.mark.parametrize('language',['es','en'])
@pytest.mark.parametrize('size',[(640,420),(720,500),(900,620)])
def test_backup_compact_retains_choices_and_paths(app,tmp_path,language,theme,size):
    set_language(language)
    design.apply_theme(app,theme)
    (tmp_path/'02').mkdir()
    (tmp_path/'02/disc.cdi').write_bytes(b'generated source')
    dialog=show(app,BackupPromptV2(diagnose_storage(tmp_path)),size)
    assert dialog.source_strip.text()==str(tmp_path)
    assert dialog.target_strip.text()==str(dialog.destination)
    assert dialog.target_strip.value.isReadOnly()
    assert dialog.target_strip.value.toolTip()==str(dialog.destination)
    assert dialog.skip_button.isVisible() and dialog.cancel_button.isVisible() and dialog.backup_button.isVisible()
    assert not dialog.remember_check.isChecked()
    assert dialog.header.artwork.isVisible()==(dialog.width()>=720 and dialog.height()>=500)
    reachable(app,dialog)
    capture(dialog,'backup_choose',language,theme)
    dispose(app,dialog)


def test_backup_skip_once_does_not_persist_and_cancel_is_inert(app,tmp_path,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import backup
    dialog=show(app,BackupPromptV2(diagnose_storage(tmp_path)))
    saved=[]
    monkeypatch.setattr(backup,'save_settings',lambda value:saved.append(value))
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Rejected)
    dialog.skip_backup()
    assert not saved and dialog.result()!=QDialog.DialogCode.Accepted
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Accepted)
    dialog.skip_backup()
    assert not saved and dialog.result()==QDialog.DialogCode.Accepted
    dispose(app,dialog)


def test_backup_remember_requires_confirmation_and_required_prompt_never_skips(app,tmp_path,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import backup
    dialog=show(app,BackupPromptV2(diagnose_storage(tmp_path)))
    saved=[]
    monkeypatch.setattr(backup,'save_settings',lambda value:saved.append(value))
    dialog.remember_check.setChecked(True)
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Rejected)
    dialog.skip_backup()
    assert not saved
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Accepted)
    dialog.skip_backup()
    assert len(saved)==1
    assert any(value['decision']=='skipped' for value in saved[0]['ui']['backup_decisions'].values())
    dispose(app,dialog)
    required=show(app,BackupPromptV2(diagnose_storage(tmp_path),allow_skip=False))
    assert required.skip_button is None and not required.remember_check.isVisible()
    required.skip_backup()
    assert required.result()!=QDialog.DialogCode.Accepted
    capture(required,'backup_required')
    dispose(app,required)


def test_confirmation_return_default_and_explicit_accept(app):
    from openmenu_gdemu_manager.ui.v2.catalog import tr
    dialog=show(app,Confirmation(None,tr('backup_skipping'),tr('backup_skip_body')+'\n\n'+tr('backup_skip_once'),tr('backup_continue')),(500,240))
    assert dialog.back_button.isDefault()
    reachable(app,dialog)
    capture(dialog,'backup_skip_confirmation')
    QTest.keyClick(dialog,Qt.Key.Key_Escape)
    assert dialog.result()==QDialog.DialogCode.Rejected
    dispose(app,dialog)


def test_real_backup_worker_success_waits_for_continue(app,tmp_path,monkeypatch):
    source=tmp_path/'source'
    source.mkdir()
    (source/'02').mkdir()
    (source/'02/disc.cdi').write_bytes(b'generated disc contents')
    (source/'02/second.bin').write_bytes(b'generated second file')
    import threading
    begin_copy,finish_copy=threading.Event(),threading.Event()
    original_copy=backup_prompt.backup_sd_contents
    def controlled_copy(source,destination,progress=None):
        assert begin_copy.wait(10)
        def observed(current,total,name):
            progress(current,total,name)
            if current==1:assert finish_copy.wait(10)
        return original_copy(source,destination,progress=observed)
    monkeypatch.setattr(backup_prompt,'backup_sd_contents',controlled_copy)
    dialog=show(app,BackupPromptV2(diagnose_storage(source)))
    dialog.destination=tmp_path/'copy'
    dialog._refresh_destination()
    monkeypatch.setattr(dialog,'_confirm_message',lambda *args:True)
    dialog.start_backup()
    assert dialog._backup_active and not dialog.cancel_button.isEnabled()
    app.processEvents()
    capture(dialog,'backup_preparing')
    begin_copy.set()
    for _ in range(600):
        if dialog.phase=='copying':break
        QTest.qWait(10)
    assert dialog.phase=='copying'
    app.processEvents()
    capture(dialog,'backup_running')
    finish_copy.set()
    dialog.close()
    assert dialog.isVisible()
    for _ in range(600):
        if not dialog._backup_active:break
        QTest.qWait(10)
    assert not dialog._backup_active and dialog.phase=='success'
    assert (dialog.destination/'02/disc.cdi').read_bytes()==b'generated disc contents'
    assert (dialog.destination/'backup_manifest.json').is_file()
    assert dialog.isVisible() and dialog.result()!=QDialog.DialogCode.Accepted
    assert dialog.continue_button.isVisible() and dialog.open_button.isVisible()
    reachable(app,dialog)
    capture(dialog,'backup_success')
    QTest.mouseClick(dialog.continue_button,Qt.MouseButton.LeftButton)
    assert dialog.result()==QDialog.DialogCode.Accepted
    dispose(app,dialog)


def test_real_backup_failure_has_details_retry_and_no_success_registry(app,tmp_path,monkeypatch):
    source=tmp_path/'source'
    source.mkdir()
    (source/'disc.cdi').write_bytes(b'generated')
    dialog=show(app,BackupPromptV2(diagnose_storage(source)))
    dialog.destination=source/'inside'
    dialog._refresh_destination()
    monkeypatch.setattr(dialog,'_confirm_message',lambda *args:True)
    dialog.start_backup()
    for _ in range(600):
        if not dialog._backup_active:break
        QTest.qWait(10)
    assert dialog.phase=='error' and dialog.failed
    assert not dialog.continue_button.isVisible() and dialog.backup_button.isVisible()
    assert dialog.choose_button.isEnabled()
    assert not (source/'inside/backup_manifest.json').exists()
    reachable(app,dialog)
    capture(dialog,'backup_failed')
    QTest.mouseClick(dialog.details_button,Qt.MouseButton.LeftButton)
    app.processEvents()
    assert dialog.details_scroll.isVisible() and dialog.details.text()
    capture(dialog,'backup_failed')
    dialog.destination=tmp_path/'retry'
    dialog._refresh_destination()
    dialog.start_backup()
    for _ in range(600):
        if not dialog._backup_active:break
        QTest.qWait(10)
    assert dialog.phase=='success' and (dialog.destination/'disc.cdi').exists()
    dispose(app,dialog)


def test_setup_real_checking_and_install_start_failure_are_visible(app,tmp_path,monkeypatch):
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(tmp_path)))
    original=setup.diagnose_storage
    def diagnose(path):
        assert dialog.phase=='checking'
        return original(path)
    monkeypatch.setattr(setup,'diagnose_storage',diagnose)
    QTimer.singleShot(0,lambda:capture(dialog,'checking'))
    dialog.run_diagnostic()
    monkeypatch.setattr(setup,'_confirm_dialog',lambda *args:True)
    def install(*args):
        assert dialog.phase=='install_running'
        raise OSError('Synthetic install failure')
    monkeypatch.setattr(setup,'install_openmenu_base',install)
    monkeypatch.setattr(setup.QMessageBox,'warning',lambda *args:None)
    QTimer.singleShot(0,lambda:capture(dialog,'install_running'))
    dialog.prepare_openmenu_base()
    assert dialog.phase=='install_failed' and dialog.isVisible() and dialog.use_button.isEnabled()
    capture(dialog,'install_failed')
    dispose(app,dialog)


@pytest.mark.parametrize('language',['es','en'])
@pytest.mark.parametrize('theme',['light','dark'])
@pytest.mark.parametrize('state',['unselected','empty','ready','readonly','legacy_upgrade_required','security_blocked','inaccessible'])
def test_setup_illustrated_states_and_disclosure(app,tmp_path,language,theme,state):
    set_language(language)
    design.apply_theme(app,theme)
    root=tmp_path/'source'
    root.mkdir()
    if state=='security_blocked':(root/'private.txt').write_text('preserve')
    if state=='inaccessible':root=root/'missing'
    if state in ('ready','readonly','legacy_upgrade_required'):
        (root/'01').mkdir()
        (root/'01/track05.iso').write_bytes(b'prefix [OPENMENU] openMenu NEODC_1 suffix' if state!='legacy_upgrade_required' else b'unknown synthetic menu')
    diagnostic=None if state=='unselected' else diagnose_storage(root)
    if state=='readonly':
        # Presentation-only permissions scenario; the real current diagnostics
        # classify incompatible menus as legacy_upgrade_required.
        diagnostic.write_allowed=False
        diagnostic.reason='Synthetic read-only permissions'
    dialog=show(app,setup.SetupWizardV2(diagnostic),(720,500))
    assert dialog.phase==state
    assert dialog.use_button.isVisible()==(state in ('empty','ready','readonly','legacy_upgrade_required'))
    assert not dialog.backup_card.isVisible()  # These fixtures have no user game content.
    reachable(app,dialog)
    capture(dialog,state,language,theme)
    if state!='unselected':
        QTest.mouseClick(dialog.details_action,Qt.MouseButton.LeftButton)
        app.processEvents()
        reachable(app,dialog)
        capture(dialog,state,language,theme)
    dispose(app,dialog)


def test_setup_backup_recommendation_and_remember_are_explicit(app,tmp_path,monkeypatch):
    (tmp_path/'01').mkdir()
    (tmp_path/'01/track05.iso').write_bytes(b'prefix [OPENMENU] openMenu NEODC_1 suffix')
    (tmp_path/'02').mkdir()
    (tmp_path/'02/disc.cdi').write_bytes(b'generated')
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(tmp_path)),(900,620))
    assert dialog.backup_card.isVisible() and not dialog.skip_backup_button.isChecked()
    reachable(app,dialog)
    capture(dialog,'ready')
    saved=[]
    monkeypatch.setattr(setup,'save_settings',lambda value:saved.append(value))
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Rejected)
    QTest.mouseClick(dialog.skip_backup_button,Qt.MouseButton.LeftButton)
    assert not saved and not dialog.skip_backup_button.isChecked() and dialog.backup_card.isVisible()
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Accepted)
    QTest.mouseClick(dialog.skip_backup_button,Qt.MouseButton.LeftButton)
    assert saved and not dialog.backup_card.isVisible()
    dispose(app,dialog)


def test_setup_installed_success_requires_continuation(app,tmp_path,monkeypatch):
    diagnostic=diagnose_storage(tmp_path)
    dialog=show(app,setup.SetupWizardV2(diagnostic))
    result=diagnose_storage(tmp_path)
    result.prepare_allowed=False
    result.scan_allowed=True
    result.write_allowed=True
    result.menu_state='openmenu_compatible'
    monkeypatch.setattr(setup,'_confirm_dialog',lambda *args:True)
    monkeypatch.setattr(setup,'install_openmenu_base',lambda *args:result)
    dialog.prepare_openmenu_base()
    assert dialog.phase=='installed' and dialog.isVisible() and dialog._installed
    assert dialog.result()!=QDialog.DialogCode.Accepted
    reachable(app,dialog)
    capture(dialog,'installed')
    dispose(app,dialog)


def test_path_enter_only_checks_and_dynamic_labels_are_accessible(app,tmp_path,monkeypatch):
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(tmp_path)))
    confirmations=[]
    monkeypatch.setattr(setup,'_confirm_dialog',lambda *args:confirmations.append(args) or False)
    dialog.route_edit.setFocus()
    QTest.keyClick(dialog.route_edit,Qt.Key.Key_Return)
    app.processEvents()
    assert not confirmations and dialog.phase=='empty'
    assert dialog.use_button.accessibleName()==dialog.use_button.text()
    assert dialog.use_button.toolTip()==dialog.use_button.text()
    dispose(app,dialog)


def test_readonly_backup_does_not_write_source_registry(app,tmp_path,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import backup
    source=tmp_path/'source'
    source.mkdir()
    (source/'02').mkdir()
    (source/'02/disc.cdi').write_bytes(b'generated')
    diagnostic=diagnose_storage(source)
    diagnostic.write_allowed=False
    diagnostic.scan_allowed=True
    monkeypatch.setattr(backup,'write_backup_registry',lambda *args:pytest.fail('read-only source registry mutated'))
    dialog=show(app,BackupPromptV2(diagnostic))
    dialog.destination=tmp_path/'copy'
    dialog._refresh_destination()
    monkeypatch.setattr(dialog,'_confirm_message',lambda *args:True)
    dialog.start_backup()
    for _ in range(600):
        if not dialog._backup_active:break
        QTest.qWait(10)
    assert dialog.phase=='success' and dialog.continue_button.isVisible()
    assert (dialog.destination/'backup_manifest.json').exists()
    assert not (source/'_openmenu_gdemu_manager').exists()
    dispose(app,dialog)


def test_real_install_incompatible_template_never_reports_success(app,tmp_path,monkeypatch):
    template=tmp_path/'template'
    (template/'01').mkdir(parents=True)
    (template/'01/README.txt').write_text('not a menu')
    destination=tmp_path/'destination'
    destination.mkdir()
    from openmenu_gdemu_manager.services import setup_service
    monkeypatch.setattr(setup_service,'configured_openmenu_template_dir',lambda settings:template)
    monkeypatch.setattr(setup,'_confirm_dialog',lambda *args:True)
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(destination)))
    dialog.prepare_openmenu_base()
    assert not dialog._installed and dialog.phase=='install_failed'
    assert not dialog.diagnostic.write_allowed
    assert dialog.result()!=QDialog.DialogCode.Accepted
    dispose(app,dialog)


def test_real_install_then_folder_picker_revokes_installed_flag(app,tmp_path,monkeypatch):
    from openmenu_gdemu_manager.services import setup_service
    from openmenu_gdemu_manager.ui.dialogs import setup_wizard
    template=tmp_path/'template'
    (template/'01').mkdir(parents=True)
    (template/'01/track05.iso').write_bytes(b'prefix [OPENMENU] openMenu NEODC_1 suffix')
    first,second=tmp_path/'first',tmp_path/'second'
    first.mkdir()
    second.mkdir()
    monkeypatch.setattr(setup_service,'configured_openmenu_template_dir',lambda settings:template)
    monkeypatch.setattr(setup,'_confirm_dialog',lambda *args:True)
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(first)))
    dialog.prepare_openmenu_base()
    assert dialog._installed and dialog.phase=='installed'
    monkeypatch.setattr(setup_wizard.QFileDialog,'getExistingDirectory',lambda *args:str(second))
    dialog.pick_route()
    assert not dialog._installed and dialog.phase=='empty'
    dialog.handle_primary_action()
    assert dialog.phase=='installed' and (second/'01/track05.iso').is_file()
    dispose(app,dialog)


def test_failed_preference_save_preserves_decision_and_reminder(app,tmp_path,monkeypatch):
    from openmenu_gdemu_manager.ui.v2 import backup
    from openmenu_gdemu_manager.services.backup_service import backup_decision
    source=tmp_path/'source'
    (source/'01').mkdir(parents=True)
    (source/'01/track05.iso').write_bytes(b'prefix [OPENMENU] openMenu NEODC_1 suffix')
    (source/'02').mkdir()
    diagnostic=diagnose_storage(source)
    def fail(*args):raise OSError('Synthetic settings failure')
    monkeypatch.setattr(backup,'save_settings',fail)
    monkeypatch.setattr(setup,'save_settings',fail)
    monkeypatch.setattr(Confirmation,'exec',lambda self:QDialog.DialogCode.Accepted)
    dialog=show(app,BackupPromptV2(diagnostic))
    dialog.remember_check.setChecked(True)
    dialog.skip_backup()
    assert not backup_decision(dialog.settings,diagnostic)
    assert dialog.preference_notice.isVisible() and dialog.isVisible()
    assert dialog.result()!=QDialog.DialogCode.Accepted
    dispose(app,dialog)
    wizard=show(app,setup.SetupWizardV2(diagnostic))
    wizard.skip_backup_for_current_sd()
    assert not backup_decision(wizard.settings,diagnostic)
    assert wizard.summary.isVisible() and wizard.backup_card.isVisible()
    other=tmp_path/'other'
    other.mkdir()
    wizard.route_edit.setText(str(other))
    wizard.run_diagnostic()
    assert not wizard.summary.isVisible()
    dispose(app,wizard)


def test_completed_local_backup_supports_legacy_gate_without_source_mutation(app,tmp_path):
    from openmenu_gdemu_manager.services.backup_service import backup_sd_contents,set_backup_decision,completed_backup_exists
    from openmenu_gdemu_manager.ui.v2.main_window import MainWindowV2
    from openmenu_gdemu_manager.services.sd_registry import registered_backup_exists
    source=tmp_path/'source'
    (source/'01').mkdir(parents=True)
    (source/'01/track05.iso').write_bytes(b'prefix [OPENMENU] legacy data suffix')
    diagnostic=diagnose_storage(source)
    assert diagnostic.legacy_menu_migratable and not diagnostic.write_allowed
    destination=backup_sd_contents(source,tmp_path/'copy')
    settings=set_backup_decision({},diagnostic,'backed_up',destination)
    assert completed_backup_exists(settings,diagnostic) and not registered_backup_exists(source)
    window=MainWindowV2.__new__(MainWindowV2)
    window.settings=settings
    assert window._has_registered_backup(diagnostic)
    wizard=setup.SetupWizardV2(diagnostic)
    wizard.settings=settings
    wizard._show_diagnostic(diagnostic)
    assert not wizard.backup_card.isVisibleTo(wizard)
    dispose(app,wizard)
    (destination/'01/track05.iso').unlink()
    assert not completed_backup_exists(settings,diagnostic)
    assert not window._has_registered_backup(diagnostic)


def test_compact_tab_scrolls_reminder_into_view(app,tmp_path):
    (tmp_path/'01').mkdir()
    (tmp_path/'01/track05.iso').write_bytes(b'prefix [OPENMENU] openMenu NEODC_1 suffix')
    (tmp_path/'02').mkdir()
    design.apply_theme(app,'dark')
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(tmp_path)),(640,420))
    dialog.body_scroll.verticalScrollBar().setValue(0)
    dialog.route_edit.setFocus()
    for _ in range(20):
        if app.focusWidget() is dialog.skip_backup_button:break
        QTest.keyClick(app.focusWidget() or dialog,Qt.Key.Key_Tab)
        app.processEvents()
    assert app.focusWidget() is dialog.skip_backup_button
    top=dialog.skip_backup_button.mapTo(dialog,dialog.skip_backup_button.rect().topLeft())
    bottom=dialog.skip_backup_button.mapTo(dialog,dialog.skip_backup_button.rect().bottomRight())
    assert dialog.rect().contains(top) and dialog.rect().contains(bottom)
    dispose(app,dialog)


def test_install_service_keeps_gui_responsive_and_guards_busy_actions(app,tmp_path,monkeypatch):
    import threading,time
    from PySide6.QtCore import QThread
    dialog=show(app,setup.SetupWizardV2(diagnose_storage(tmp_path)))
    monkeypatch.setattr(setup,'_confirm_dialog',lambda *args:True)
    gui_thread=QThread.currentThread()
    started=threading.Event()
    observed=[]
    def slow_install(*args):
        assert QThread.currentThread()!=gui_thread
        started.set()
        time.sleep(.15)
        raise OSError('Synthetic delayed failure')
    def tick():
        if not started.is_set() or not dialog._install_active:return
        observed.append(dialog._install_active)
        dialog.close()
        assert dialog.isVisible() and not dialog.cancel_button.isEnabled()
        dialog.handle_primary_action()
    timer=QTimer(dialog)
    timer.setInterval(10)
    timer.timeout.connect(tick)
    timer.start()
    monkeypatch.setattr(setup,'install_openmenu_base',slow_install)
    monkeypatch.setattr(setup.QMessageBox,'warning',lambda *args:None)
    dialog.prepare_openmenu_base()
    timer.stop()
    assert observed and all(observed) and dialog.phase=='install_failed'
    dispose(app,dialog)


@pytest.mark.parametrize('language',['es','en'])
def test_preparation_catalog_has_all_visible_strings_in_both_languages(app,language):
    import ast
    set_language(language)
    root=Path(__file__).resolve().parents[1]/'src/openmenu_gdemu_manager'
    data=json.loads((root/f'resources/i18n/{language}.json').read_text(encoding='utf-8'))
    assert not any(key.startswith('v2.') for key in data)
    for file in ('preparation.py','setup.py','backup.py'):
        tree=ast.parse((root/'ui/v2'/file).read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id=='tr' and node.args and isinstance(node.args[0],ast.Constant):
                key='v2.'+node.args[0].value
                assert key in data['strings'],(language,file,key)
    for key in ('backup_required_intro','backup_preferences_warning','backup_registry_warning','setup_install_incompatible','backup_error_inside','backup_error_source','backup_preferences_failed'):
        assert 'v2.'+key in data['strings']


@pytest.mark.parametrize('language',['es','en'])
@pytest.mark.parametrize('theme',['light','dark'])
@pytest.mark.parametrize('remember',[False,True])
def test_compact_confirmation_complete_text_is_keyboard_reachable(app,language,theme,remember):
    from openmenu_gdemu_manager.ui.v2.catalog import tr
    from openmenu_gdemu_manager.ui.v2.preparation import StatusCard
    set_language(language)
    design.apply_theme(app,theme)
    text=tr('backup_skip_body')+'\n\n'+tr('backup_skip_remembered' if remember else 'backup_skip_once')
    dialog=show(app,Confirmation(None,tr('backup_skipping'),text,tr('backup_continue')),(500,240))
    QTest.qWait(50)
    card=next(item for item in dialog.findChildren(QWidget) if isinstance(item,StatusCard))
    for item in (card.title,card.message):
        assert item.height()>=item.heightForWidth(item.width())
    dialog.back_button.setFocus()
    QTest.keyClick(dialog.back_button,Qt.Key.Key_Backtab)
    assert app.focusWidget() is dialog.body_scroll
    for _ in range(5):QTest.keyClick(dialog.body_scroll,Qt.Key.Key_PageDown)
    app.processEvents()
    viewport=dialog.body_scroll.viewport()
    bottom=card.message.mapTo(viewport,card.message.rect().bottomLeft())
    assert viewport.rect().contains(bottom),bottom
    assert dialog.back_button.isVisible() and dialog.continue_button.isVisible()
    capture(dialog,'backup_skip_confirmation',language,theme)
    dispose(app,dialog)


@pytest.mark.parametrize('language',['es','en'])
def test_confirmation_opens_tall_enough_for_its_whole_message(app,language):
    from openmenu_gdemu_manager.ui.v2.catalog import tr
    set_language(language)
    messages=[tr('backup_skip_body')+'\n\n'+tr(key) for key in ('backup_skip_once','backup_skip_remembered')]
    for message in messages:
        dialog=Confirmation(None,tr('backup_skipping'),message,tr('backup_continue'))
        dialog.show();app.processEvents()
        assert dialog.body_scroll.verticalScrollBar().maximum()==0,(message,dialog.size())
        assert dialog.width()==500 and dialog.height()>=220
        reachable(app,dialog)
        dispose(app,dialog)
