from dataclasses import replace
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox

from comparador.engine import scan
from comparador.models import Match, ScanOptions
from comparador.operations import execute_actions, plan_actions
from comparador.settings import Preferences, load_preferences, save_preferences, RESULT_COLUMNS
from comparador.preferences_dialog import PreferencesDialog
from comparador.ui import MainWindow


def visual_sample(roots, tmp_path):
    folder, _ = roots
    for number, name in enumerate(('Ocean original.dat', 'Ocean compressed.dat', 'Ocean edited.dat')):
        (folder / name).write_bytes(bytes([number]) * (number + 5))
    result = scan(ScanOptions(folder), cache_path=tmp_path / 'cache.db')
    records = sorted(result.files.values(), key=lambda f: f.relative)
    a, b, c = (f.key for f in records)
    result.options.similar = True
    result.similar_matches = [Match(a, b, 'similar', 97, 93), Match(b, c, 'similar', 95, 88)]
    return result, (a, b, c)


def show_pair(window, a, b):
    row = window.visible_keys().index(a)
    window.table.setCurrentCell(row, 1)
    window.show_details()
    index = next(i for i, (peer, _) in enumerate(window.peer_entries) if peer.key == b)
    window.peer_combo.setCurrentIndex(index)


def test_one_folder_filters_exclude_two_folder_options(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    assert [window.view_filter.itemData(i) for i in range(window.view_filter.count())] == [0, 1, 2, 7, 8]
    window.folder_mode.setCurrentIndex(1)
    assert window.view_filter.findData(3) >= 0
    window.view_filter.setCurrentIndex(window.view_filter.findData(3))
    result, _ = visual_sample(roots, tmp_path)
    window.scan_done(result)
    assert window.view_filter.currentData() == 0
    assert window.scope_filter.currentData() == 1
    assert window.scope_filter.isHidden()
    assert window.scope_label.isHidden()
    assert window.unlock.isHidden()
    assert window.metrics[3].isHidden()
    assert all('secundaria' not in window.view_filter.itemText(i).lower() for i in range(window.view_filter.count()))
    assert window.table.rowCount() == 3
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_one_folder_visual_choice_reaches_confirmed_trash(qtbot, roots, tmp_path, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    result, (a, b, _) = visual_sample(roots, tmp_path)
    window.scan_done(result)
    window.view_filter.setCurrentIndex(window.view_filter.findData(2))
    show_pair(window, a, b)
    qtbot.mouseClick(window.left_preview.keep, Qt.MouseButton.LeftButton)
    assert window.checked_keys == {b}
    assert window.choose_keepers([b]) == {b: a}
    dialogs = []
    monkeypatch.setattr(QDialog, 'exec', lambda dialog: dialogs.append(dialog.windowTitle()) or QDialog.DialogCode.Accepted)
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: pytest.fail(str(args)))
    outcomes = []
    monkeypatch.setattr('comparador.ui.execute_actions', lambda r, actions, kind, cancel, progress: execute_actions(
        r, actions, kind, cancel, progress, trash_func=lambda path: Path(path).unlink()))
    monkeypatch.setattr(window, 'start_job', lambda fn, completed: outcomes.extend(fn(None, lambda *args: None)))
    window.trash_selected()
    assert len(dialogs) == 1
    assert all(outcome['ok'] for outcome in outcomes) and len(outcomes) == 1
    assert Path(result.files[a].path).exists()
    assert not Path(result.files[b].path).exists()
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_replacing_a_reference_keeps_earlier_dependents(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result, (a, b, c) = visual_sample(roots, tmp_path)
    window.scan_done(result)
    show_pair(window, a, b)
    window.choose_preview(False)  # Keep b, remove a.
    assert window.checked_keys == {a}
    show_pair(window, b, c)
    window.choose_preview(False)  # Keep c, remove b. a has no direct match with c.
    assert window.checked_keys == {b}
    assert window.preferred_keepers == {b: c}
    assert window.choose_keepers([b]) == {b: c}
    assert plan_actions(result, [b], 'trash', keepers=window.choose_keepers([b]))[0].keeper == c
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_all_visual_copies_selected_reports_specific_paths(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result, (a, b, c) = visual_sample(roots, tmp_path)
    window.scan_done(result)
    with pytest.raises(ValueError) as error:
        window.keeper_dialog([a, b, c])
    assert Path(result.files[a].path).name in str(error.value)
    assert result.files[b].path in str(error.value)
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_changing_reference_after_checkbox_selection_keeps_orphaned_match(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result, (a, b, c) = visual_sample(roots, tmp_path)
    window.scan_done(result)
    window.set_checked({a})
    show_pair(window, b, c)
    window.choose_preview(False)
    assert window.checked_keys == {b}
    assert window.choose_keepers([b]) == {b: c}
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_list_names_each_direct_match_and_shows_decisions(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result, (a, b, c) = visual_sample(roots, tmp_path)
    window.scan_done(result)
    row = window.visible_keys().index(a)
    assert Path(result.files[b].path).name in window.table.item(row, 2).text()
    assert 'V001' in window.table.item(row, 2).text()
    assert result.files[b].path in window.table.item(row, 2).toolTip()
    row = window.visible_keys().index(b)
    assert result.files[c].path in window.table.item(row, 2).toolTip()
    assert 'V002' in window.table.item(row, 2).toolTip()
    show_pair(window, a, b)
    window.choose_preview(True)
    for key, text in [(a, 'Conservar'), (b, 'Retirar')]:
        row = window.visible_keys().index(key)
        assert window.table.item(row, 0).text() == text
    # Theme/language changes preserve the reviewed copy and the result filter.
    window.view_filter.setCurrentIndex(window.view_filter.findData(2))
    window.apply_preferences(replace(window.preferences, language='en'))
    assert window.preferred_keepers == {b: a}
    assert window.view_filter.currentData() == 2
    assert window.choose_keepers([b]) == {b: a}
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_comparison_toggle_stays_available_and_buttons_fill_width(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result, _ = visual_sample(roots, tmp_path)
    window.scan_done(result)
    window.show()
    qtbot.waitUntil(lambda: not window.preview_scroll.isHidden())
    qtbot.mouseClick(window.comparison_toggle, Qt.MouseButton.LeftButton)
    assert window.preview_scroll.isHidden()
    assert window.comparison_toggle.isVisible()
    assert window.comparison_toggle.text() == 'Mostrar comparación'
    qtbot.mouseClick(window.comparison_toggle, Qt.MouseButton.LeftButton)
    assert not window.preview_scroll.isHidden()
    assert window.comparison_toggle.text() == 'Ocultar comparación'
    for card in [window.left_preview, window.right_preview]:
        assert abs(card.keep.width() - card.remove.width()) <= 1
        assert card.remove.geometry().right() >= card.width() - 16
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_result_columns_persist_and_apply_to_existing_comparison(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result, (a, b, _) = visual_sample(roots, tmp_path)
    window.scan_done(result)
    show_pair(window, a, b)
    window.choose_preview(True)
    dialog = PreferencesDialog(window.preferences)
    qtbot.addWidget(dialog)
    assert dialog.column_checks['file'].isChecked() and not dialog.column_checks['file'].isEnabled()
    assert dialog.column_checks['remove'].isChecked() and not dialog.column_checks['remove'].isEnabled()
    for key in ('duration', 'resolution', 'scores'):
        dialog.column_checks[key].setChecked(False)
    updated = dialog.preferences()
    path = tmp_path / 'appdata' / 'settings.json'
    save_preferences(updated, path)
    assert load_preferences(path) == updated
    window.apply_preferences(updated)
    for index, (key, _) in enumerate(RESULT_COLUMNS):
        assert window.table.isColumnHidden(index) == (key not in updated.visible_columns)
    assert window.checked_keys == {b}
    assert window.preferred_keepers == {b: a}
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.table.isColumnHidden(5)
    assert not reopened.table.isColumnHidden(1)
    qtbot.mouseClick(dialog.restore_columns, Qt.MouseButton.LeftButton)
    assert dialog.preferences().visible_columns == [key for key, _ in RESULT_COLUMNS]
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


@pytest.mark.parametrize('columns', [[], ['file'], ['file', 'remove', 'unknown'], ['file', 'remove', 'file'], 'file'])
def test_invalid_column_preferences_cannot_hide_required_columns(columns):
    with pytest.raises(ValueError):
        Preferences(visible_columns=columns).validate()


def test_large_group_lists_counts_without_unbounded_tooltips(qtbot, roots, tmp_path):
    folder, _ = roots
    for index in range(25):
        (folder / f'copy-{index:02d}.dat').write_bytes(b'same content')
    result = scan(ScanOptions(folder), cache_path=tmp_path / 'cache.db')
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(result)
    assert window.table.rowCount() == 25
    assert '+23' in window.table.item(0, 2).text()
    assert window.table.item(0, 2).toolTip().count('G001:') == 20
    assert len(window.peer_entries) == 24
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)
