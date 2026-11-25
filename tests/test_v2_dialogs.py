"""Retained-dialog design coverage, not merely presence of controller methods."""
from pathlib import Path
import os

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QMessageBox, QInputDialog, QLabel, QTableWidget

from openmenu_gdemu_manager.i18n import set_language, active_language, available_languages
from openmenu_gdemu_manager.dreamcast.storage_diagnostics import diagnose_storage
from openmenu_gdemu_manager.ui.v2 import design, setup
from openmenu_gdemu_manager.ui.v2.retained_dialogs import RETAINED_DIALOGS
from openmenu_gdemu_manager.ui.dialogs import backup_prompt
from openmenu_gdemu_manager.ui.dialogs.legacy_upgrade import LegacyMenuUpgradeDialog
from openmenu_gdemu_manager.ui.dialogs.confirm_apply import ConfirmApplyDialog
from openmenu_gdemu_manager.ui.dialogs.provider_settings import ProviderSettingsDialog, ProviderConfigDialog
from openmenu_gdemu_manager.ui.dialogs.language_selection import LanguageSelectionDialog
from openmenu_gdemu_manager.ui.dialogs.about import AboutDialog
from openmenu_gdemu_manager.ui.dialogs.bulk_progress import BulkProgressDialog


@pytest.fixture
def app():
    instance = QApplication.instance() or QApplication([])
    previous = active_language()
    set_language('es')
    design.apply_theme(instance)
    yield instance
    set_language(previous)


def _show(app, dialog, size=None):
    if size:
        dialog.resize(*size)
    dialog.show()
    app.processEvents()
    return dialog


def _dispose(app, dialog):
    if isinstance(dialog, BulkProgressDialog):
        dialog.spinner.stop()
        dialog.accept()
    else:
        dialog.hide()
    dialog.deleteLater()
    app.processEvents()


def _capture(dialog, name):
    folder = os.environ.get('OPENMENU_V2_CAPTURE_DIR')
    if folder:
        target = Path(folder)
        target.mkdir(parents=True, exist_ok=True)
        assert dialog.grab().save(str(target / (name + '.png')))


def _visible_buttons_reachable(dialog):
    for button in dialog.findChildren(QPushButton):
        if not button.isVisibleTo(dialog):
            continue
        assert button.accessibleName(), (type(dialog).__name__, button.text())
        if any(table.isAncestorOf(button) for table in dialog.findChildren(QTableWidget)):
            # Table cells are intentionally scrollable, unlike the fixed footer.
            continue
        point = button.mapTo(dialog, button.rect().bottomRight())
        assert dialog.rect().contains(point), (type(dialog).__name__, button.text(), point, dialog.size())


@pytest.mark.parametrize('size', [(640, 420), (720, 500), (900, 620)])
@pytest.mark.parametrize('state', ['choose', 'empty', 'blocked', 'readonly', 'ready'])
def test_setup_states_hierarchy_disclosure_and_footer(app, tmp_path, size, state):
    destination = tmp_path / 'destination'
    destination.mkdir()
    if state == 'blocked':
        (destination / 'personal.txt').write_text('unrelated content')
    diagnostic = None if state == 'choose' else diagnose_storage(destination)
    if state in ('readonly', 'ready'):
        diagnostic.prepare_allowed = False
        diagnostic.scan_allowed = True
        diagnostic.write_allowed = state == 'ready'
        diagnostic.menu_state = 'openmenu_compatible' if state == 'ready' else 'gdmenu_basic'
    dialog = _show(app, setup.SetupWizardV2(diagnostic), size)
    assert dialog.security_card.objectName() == 'Card'
    assert not dialog.details_scroll.isVisible()
    assert dialog.security_title.text() and dialog.security_message.text()
    assert dialog.use_button.isVisible() == (state in ('empty', 'readonly', 'ready'))
    assert dialog.pick_other_button.property('role') == ('primary' if state in ('choose', 'blocked') else 'secondary')
    _visible_buttons_reachable(dialog)
    _capture(dialog, f'setup-{state}-{size[0]}x{size[1]}')
    if state != 'choose':
        QTest.mouseClick(dialog.details_action, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert dialog.details_scroll.isVisible()
        _visible_buttons_reachable(dialog)
        assert not any(not item.pixmap().isNull() for item in dialog.details_scroll.findChildren(QLabel))
        _capture(dialog, f'setup-{state}-details-{size[0]}x{size[1]}')
    _dispose(app, dialog)


def test_setup_revalidates_edited_path_and_blocks_stale_acceptance(app, tmp_path, monkeypatch):
    source = tmp_path / 'empty'
    source.mkdir()
    blocked = tmp_path / 'blocked'
    blocked.mkdir()
    (blocked / 'personal.txt').write_text('keep')
    dialog = setup.SetupWizardV2(diagnose_storage(source))
    calls = []
    monkeypatch.setattr(setup, 'install_openmenu_base', lambda *args: calls.append(args))
    dialog.route_edit.setText(str(blocked))
    dialog.handle_primary_action()
    assert not calls and dialog.result() != QDialog.DialogCode.Accepted
    assert dialog.diagnostic.root == blocked and not dialog.diagnostic.prepare_allowed
    assert (blocked / 'personal.txt').read_text() == 'keep'
    _dispose(app, dialog)


def test_setup_install_result_stays_visible_until_continue(app, tmp_path, monkeypatch):
    dialog = _show(app, setup.SetupWizardV2(diagnose_storage(tmp_path)))
    result = diagnose_storage(tmp_path)
    result.prepare_allowed = False
    result.scan_allowed = result.write_allowed = True
    result.menu_state = 'openmenu_compatible'
    monkeypatch.setattr(setup, '_confirm_dialog', lambda *args: True)
    monkeypatch.setattr(setup, 'install_openmenu_base', lambda *args: result)
    monkeypatch.setattr(setup, 'diagnose_storage', lambda *args: result if dialog._installed else dialog.diagnostic)
    dialog.handle_primary_action()
    assert dialog.isVisible() and dialog.result() != QDialog.DialogCode.Accepted
    assert 'correctamente' in dialog.security_title.text()
    _capture(dialog, 'setup-installed-success')
    dialog.handle_primary_action()
    assert dialog.result() == QDialog.DialogCode.Accepted and dialog.selected_path == tmp_path
    _dispose(app, dialog)


def test_setup_cancelled_and_failed_install_never_accepts(app, tmp_path, monkeypatch):
    dialog = _show(app, setup.SetupWizardV2(diagnose_storage(tmp_path)))
    monkeypatch.setattr(setup, '_confirm_dialog', lambda *args: False)
    calls = []
    monkeypatch.setattr(setup, 'install_openmenu_base', lambda *args: calls.append(args))
    dialog.handle_primary_action()
    assert not calls and dialog.result() != QDialog.DialogCode.Accepted
    monkeypatch.setattr(setup, '_confirm_dialog', lambda *args: True)
    def fail(*args):
        raise OSError('Synthetic failure')
    monkeypatch.setattr(setup, 'install_openmenu_base', fail)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: None)
    dialog.handle_primary_action()
    assert dialog.isVisible() and dialog.result() != QDialog.DialogCode.Accepted
    _dispose(app, dialog)


def test_setup_backup_blocks_route_close_and_primary(app, tmp_path):
    dialog = _show(app, setup.SetupWizardV2(diagnose_storage(tmp_path)))
    dialog._backup_active = True
    dialog.reject()
    dialog.close()
    dialog.handle_primary_action()
    assert dialog.isVisible() and dialog.result() != QDialog.DialogCode.Accepted
    dialog._backup_active = False
    _dispose(app, dialog)


def retained_cases(tmp_path):
    diagnostic = diagnose_storage(tmp_path)
    yield 'upgrade', LegacyMenuUpgradeDialog(False)
    yield 'review', ConfirmApplyDialog(tmp_path, 3, 2, 1, slot_moves=4, product_updates=5)
    yield 'providers', ProviderSettingsDialog({})
    yield 'credentials', ProviderConfigDialog('screenscraper', 'ScreenScraper', {'cover_providers': {'screenscraper': {'ssid': 'user', 'sspassword': 'secret', 'timeout': 30}}})
    yield 'language', LanguageSelectionDialog(available_languages())
    yield 'about', AboutDialog()
    yield 'progress', BulkProgressDialog(3)


def test_every_retained_class_has_real_visual_adapter(app, tmp_path):
    seen = set()
    for name, dialog in retained_cases(tmp_path):
        _show(app, dialog)
        assert dialog.property('v2Retained') and dialog.property('v2LayoutAdapted'), name
        assert type(dialog).__name__ in RETAINED_DIALOGS
        seen.add(type(dialog).__name__)
        _visible_buttons_reachable(dialog)
        for button in dialog.findChildren(QPushButton):
            if button.isVisibleTo(dialog) and button.text():
                assert not button.icon().isNull(), (name, button.text())
        if name == 'review':
            assert (dialog.covers, dialog.additions, dialog.deletions, dialog.slot_moves, dialog.product_updates) == (3, 2, 1, 4, 5)
        if name == 'providers':
            table = dialog.table
            for row in range(table.rowCount()):
                for col in (3, 4, 5, 6):
                    cell = table.cellWidget(row, col)
                    assert cell.width() <= table.columnWidth(col)
                    # Scroll to the real row and column before checking its controls.
                    table.verticalScrollBar().setValue(row)
                    table.horizontalScrollBar().setValue(max(0, table.columnViewportPosition(col)))
                    app.processEvents()
                    point = cell.mapTo(table.viewport(), cell.rect().center())
                    assert table.viewport().rect().contains(point), (row, col, point)
            table.verticalScrollBar().setValue(0)
            table.horizontalScrollBar().setValue(0)
        _capture(dialog, name)
        _dispose(app, dialog)
    assert seen == set(RETAINED_DIALOGS)


def test_message_roles_defaults_and_template_input_are_preserved(app):
    dialog = QMessageBox()
    accept = dialog.addButton('Continue', QMessageBox.ButtonRole.AcceptRole)
    cancel = dialog.addButton('Cancel', QMessageBox.ButtonRole.RejectRole)
    destructive = dialog.addButton('Revert', QMessageBox.ButtonRole.DestructiveRole)
    dialog.setDefaultButton(cancel)
    _show(app, dialog)
    assert dialog.defaultButton() is cancel
    assert accept.property('role') == 'primary' and destructive.property('role') == 'danger'
    assert not accept.icon().isNull()
    _dispose(app, dialog)
    prompt = _show(app, QInputDialog())
    assert prompt.property('v2Retained')
    assert all(not button.icon().isNull() for button in prompt.findChildren(QPushButton))
    _dispose(app, prompt)


def test_spanish_native_message_and_input_buttons(app):
    message = QMessageBox()
    message.setStandardButtons(QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel)
    _show(app, message)
    assert message.button(QMessageBox.StandardButton.Ok).text() == 'Aceptar'
    assert message.button(QMessageBox.StandardButton.Cancel).text() == 'Cancelar'
    _dispose(app, message)
    prompt = _show(app, QInputDialog())
    assert prompt.okButtonText() == 'Aceptar' and prompt.cancelButtonText() == 'Cancelar'
    _dispose(app, prompt)


def test_backup_cancel_and_close_wait_for_worker_cleanup(app, tmp_path):
    dialog = _show(app, backup_prompt.BackupPromptDialog(diagnose_storage(tmp_path)))
    dialog._backup_active = True
    dialog._set_busy(True, '')
    assert not dialog.cancel_button.isEnabled()
    dialog.reject()
    dialog.close()
    assert dialog.isVisible()
    dialog._backup_stopped()
    assert dialog.cancel_button.isEnabled()
    dialog.reject()
    assert not dialog.isVisible()
    _dispose(app, dialog)


def test_legacy_dialogs_are_not_adapted_without_v2(app):
    app.setProperty('v2Design', False)
    # The filter must be inert for the --legacy-ui fallback in a shared process.
    dialog = LegacyMenuUpgradeDialog(False)
    _show(app, dialog)
    assert not dialog.property('v2Retained')
    _dispose(app, dialog)
    app.setProperty('v2Design', True)


def test_all_original_dialog_exports_have_explicit_v2_disposition():
    import inspect
    from openmenu_gdemu_manager.ui import dialogs
    exported = {name for name, item in inspect.getmembers(dialogs, inspect.isclass) if issubclass(item, QDialog)}
    replaced = {'BackupPromptDialog', 'SetupWizardDialog', 'CandidateDialog', 'CoverPreviewDialog', 'AddGameDialog'}
    assert exported == (set(RETAINED_DIALOGS) - {'ProviderConfigDialog'}) | replaced


@pytest.mark.parametrize('language', ['es', 'en'])
@pytest.mark.parametrize('config_text,expected', [(None, 'missing'), ('open_time=149\n', 'invalid'), ('open_time=150\nread_limit=-1\n', 'valid'), ('future_key=1\n', 'review')])
def test_setup_configuration_is_localized_reachable_and_preserved(app, tmp_path, language, config_text, expected):
    set_language(language)
    slot = tmp_path / '01'
    slot.mkdir()
    (slot / 'track05.iso').write_bytes(b'[OPENMENU] openMenu NEODC_1')
    path = tmp_path / 'GDEMU.ini'
    if config_text is not None:
        path.write_text(config_text, encoding='utf-8')
    diagnostic = diagnose_storage(tmp_path)
    assert diagnostic.configuration.status == expected
    dialog = _show(app, setup.SetupWizardV2(diagnostic), (720, 500))
    assert dialog.configuration_note.isVisible() == (expected != 'valid')
    assert dialog.use_button.isEnabled() and diagnostic.write_allowed
    QTest.mouseClick(dialog.details_action, Qt.MouseButton.LeftButton)
    app.processEvents()
    assert 'GDEMU.ini' in dialog.details.text() and 'v2.gdemu_config.' not in dialog.details.text()
    _visible_buttons_reachable(dialog)
    _capture(dialog, f'setup-config-{expected}-{language}')
    if config_text is not None:
        assert path.read_text(encoding='utf-8') == config_text
    _dispose(app, dialog)


def test_configuration_values_are_escaped_and_unknown_state_is_cleared(app, tmp_path):
    from openmenu_gdemu_manager.ui.v2 import configuration
    from openmenu_gdemu_manager.dreamcast.gdemu_config import inspect_gdemu_config
    path = tmp_path / 'GDEMU.ini'
    path.write_text('open_time=<b>bad</b>\n')
    rendered = configuration.details(inspect_gdemu_config(tmp_path))
    assert '&lt;b&gt;bad&lt;/b&gt;' in rendered and '<b>bad</b>' not in rendered
    dialog = _show(app, setup.SetupWizardV2(diagnose_storage(tmp_path)))
    dialog._route_edited('')
    assert not dialog.configuration_note.isVisible()
    _dispose(app, dialog)



def test_configuration_large_repeated_input_has_bounded_presentation(app, tmp_path):
    from openmenu_gdemu_manager.ui.v2 import configuration
    path=tmp_path/'GDEMU.ini'
    text='open_time=0\n'*5400
    path.write_bytes(text.encode('utf-8'))
    diagnostic=diagnose_storage(tmp_path)
    assert len(diagnostic.configuration.findings)>10000
    html=configuration.details(diagnostic.configuration)
    assert html.count('<br>') < 50 and len(html)<15000
    dialog=_show(app, setup.SetupWizardV2(diagnostic),(720,500))
    QTest.mouseClick(dialog.details_action,Qt.MouseButton.LeftButton)
    app.processEvents()
    _visible_buttons_reachable(dialog)
    _capture(dialog,'setup-config-many-lines')
    assert path.read_text()==text
    _dispose(app,dialog)


@pytest.mark.parametrize('language,labels', [
    ('es', ('Autor:', 'Errores y sugerencias:', 'Seguridad')),
    ('en', ('Author:', 'Bugs and suggestions:', 'Security')),
])
def test_about_names_the_author_and_where_to_report(app, language, labels):
    set_language(language)
    dialog = _show(app, AboutDialog())
    text = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
    for expected in labels + ('Ricardo Melo', 'https://ricardomelog.com', '/issues', '/security/advisories/new'):
        assert expected in text, expected
    assert 'Contacto:' not in text and 'Contact:' not in text
    body = max(dialog.findChildren(QLabel), key=lambda label: len(label.text()))
    assert body.height() >= body.heightForWidth(body.width())
    _dispose(app, dialog)


CONFIRM_TILES = ('covers', 'additions', 'deletions', 'slot_moves', 'product_updates', 'rebuild')


def _confirm(app, *counts, **kwargs):
    covers, additions, deletions, slot_moves, product_updates = counts
    return _show(app, ConfirmApplyDialog(Path('E:/'), covers, additions, deletions,
                                         slot_moves=slot_moves, product_updates=product_updates, **kwargs))


def _tile_values(dialog):
    return {key: dialog.tiles[key].value_label.text() for key in CONFIRM_TILES}


def _labels_fit(dialog):
    # Values and labels must be readable at 1x and 2.5x, never clipped.
    for key, tile in dialog.tiles.items():
        for label in (tile.title_label, tile.value_label):
            assert label.isVisible(), key
            assert tile.rect().contains(label.geometry()), (key, label.text())
            if label.wordWrap():
                assert label.height() >= label.heightForWidth(label.width()), (key, label.text())
            else:
                assert label.width() >= label.sizeHint().width(), (key, label.text())


@pytest.mark.parametrize('language', ['es', 'en'])
def test_confirm_apply_counts_every_tile_and_dims_zeros(app, language):
    set_language(language)
    dialog = _confirm(app, 2, 2, 0, 0, 0)
    values = _tile_values(dialog)
    rebuilt = {'es': 'Se reconstruye', 'en': 'Rebuilt'}[language]
    # Ricardo's option A keeps every tile, zeros included, plus the menu rebuild.
    assert values == {'covers': '2', 'additions': '2', 'deletions': '0', 'slot_moves': '0',
                      'product_updates': '0', 'rebuild': rebuilt}
    for key in ('deletions', 'slot_moves', 'product_updates'):
        assert dialog.tiles[key].value_label.property('zero') is True, key
        assert dialog.tiles[key].property('plate') == 'zero', key
    for key in ('covers', 'additions'):
        assert dialog.tiles[key].value_label.property('zero') is False, key
        assert dialog.tiles[key].property('plate') != 'zero', key
    assert dialog.tiles['deletions'].title_label.text() == {'es': 'A la papelera', 'en': 'To internal trash'}[language]
    _labels_fit(dialog)
    _dispose(app, dialog)


@pytest.mark.parametrize('language,singular,plural', [
    ('es', ('compactará 1 carpeta para', 'corregirá 1 Product ID', 'guardará 1 carátula,', 'copiará 1 juego,', 'moverá 1 juego a la papelera'),
           ('compactará 4 carpetas', 'corregirá 5 Product ID', 'guardará 3 carátulas', 'copiará 2 juegos', 'moverá 6 juegos')),
    ('en', ('compact 1 folder to', 'fix 1 Product ID value,', 'save 1 cover,', 'copy 1 game,', 'move 1 game to'),
           ('compact 4 folders', 'fix 5 Product ID values', 'save 3 covers', 'copy 2 games', 'move 6 games')),
])
def test_confirm_apply_uses_real_plurals(app, language, singular, plural):
    set_language(language)
    for counts, expected in (((1, 1, 1, 1, 1), singular), ((3, 2, 6, 4, 5), plural)):
        dialog = _confirm(app, *counts)
        text = '\n'.join(label.text() for label in dialog.findChildren(QLabel))
        assert '(s)' not in text
        for fragment in expected:
            assert fragment in dialog.message_label.text(), (counts, fragment)
        _labels_fit(dialog)
        _dispose(app, dialog)


def test_confirm_apply_cancel_stays_the_default(app):
    for counts in ((1, 0, 0, 0, 0), (3, 2, 1, 4, 5), (0, 0, 7, 12, 0)):
        dialog = _confirm(app, *counts)
        assert dialog.cancel_button.isDefault() and not dialog.apply_button.isDefault()
        assert not dialog.apply_button.autoDefault()
        QTest.keyClick(dialog, Qt.Key.Key_Return)
        app.processEvents()
        assert dialog.result() == QDialog.DialogCode.Rejected and not dialog.isVisible()
        dialog.deleteLater()
        app.processEvents()


def test_confirm_apply_does_not_count_new_game_covers_twice(app):
    set_language('es')
    # Two new games, each with its chosen cover: two games, not four changes.
    dialog = _confirm(app, 2, 2, 0, 0, 0, new_game_covers=2)
    assert _tile_values(dialog)['covers'] == '0' and dialog.tiles['covers'].value_label.property('zero') is True
    assert _tile_values(dialog)['additions'] == '2'
    assert dialog.tiles['additions'].detail_label.text() == 'incluye 2 carátulas'
    assert 'carátula' not in dialog.message_label.text() and 'copiará 2 juegos' in dialog.message_label.text()
    _labels_fit(dialog)
    _capture(dialog, 'review-new-game-covers')
    _dispose(app, dialog)
    # One existing game with a new cover plus one new game with its cover.
    dialog = _confirm(app, 2, 1, 0, 0, 0, new_game_covers=1)
    assert _tile_values(dialog)['covers'] == '1' and _tile_values(dialog)['additions'] == '1'
    assert dialog.tiles['additions'].detail_label.text() == 'incluye 1 carátula'
    assert 'guardará 1 carátula,' in dialog.message_label.text()
    _dispose(app, dialog)
    # Without new-game covers there is no extra line.
    dialog = _confirm(app, 2, 2, 0, 0, 0)
    assert not hasattr(dialog.tiles['additions'], 'detail_label')
    _dispose(app, dialog)


def test_confirm_apply_safety_line_and_large_operation_warning(app):
    dialog = _confirm(app, 1, 1, 0, 0, 0)
    assert dialog.note_label.objectName() == 'ApplySafetyText'
    assert not dialog.findChildren(QLabel, 'ChipInfo')
    _dispose(app, dialog)
    dialog = _confirm(app, 0, 0, 7, 12, 0)
    assert dialog.note_label.objectName() == 'ChipWarning'
    _dispose(app, dialog)


def test_tr_count_falls_back_to_the_language_plural(monkeypatch):
    from dataclasses import replace
    from openmenu_gdemu_manager.i18n import registry, tr_count
    reg = registry()
    package = replace(reg.languages['en'], code='xx', strings={'dialog.confirm_apply.action_add': 'xx {count}'})
    monkeypatch.setitem(reg.languages, 'xx', package)
    previous = active_language()
    set_language('xx')
    try:
        assert tr_count('dialog.confirm_apply.action_add', 1) == 'xx 1'
        assert tr_count('dialog.confirm_apply.action_covers', 1) == 'will save 1 cover'
    finally:
        set_language(previous)
