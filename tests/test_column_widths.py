from dataclasses import replace

import pytest
from PySide6.QtCore import Qt, QPoint
from PySide6.QtWidgets import QHeaderView

from comparador.settings import Preferences, load_preferences, DEFAULT_COLUMN_WIDTHS
from comparador.preferences_dialog import PreferencesDialog
from comparador.ui import MainWindow


def test_drag_and_double_click_resize_without_selecting_files(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    header = window.table.horizontalHeader()
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive
    before = header.sectionSize(1)
    edge = header.sectionViewportPosition(1) + before - 1
    qtbot.mouseMove(header.viewport(), QPoint(edge, 15))
    qtbot.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(edge, 15))
    qtbot.mouseMove(header.viewport(), QPoint(edge + 65, 15))
    qtbot.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(edge + 65, 15))
    assert header.sectionSize(1) > before
    edge = header.sectionViewportPosition(1) + header.sectionSize(1) - 1
    qtbot.mouseDClick(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(edge, 15))
    assert header.sectionSize(1) < before
    assert not window.checked_keys
    qtbot.waitUntil(lambda: not window.column_width_timer.isActive())


def test_saved_widths_survive_restart_settings_and_hidden_columns(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.table.setColumnWidth(1, 380)
    window.table.setColumnWidth(5, 140)
    qtbot.waitUntil(lambda: load_preferences().column_widths.get('file') == 380)
    assert load_preferences().column_widths['duration'] == 140
    window.apply_preferences(replace(window.preferences, language='en', visible_columns=['remove', 'file', 'matches']))
    assert window.table.columnWidth(1) == 380
    assert window.preferences.column_widths['duration'] == 140
    window.apply_preferences(replace(window.preferences, visible_columns=list(DEFAULT_COLUMN_WIDTHS)))
    assert window.table.columnWidth(5) == 140
    reopened = MainWindow()
    qtbot.addWidget(reopened)
    assert reopened.table.columnWidth(1) == 380
    assert reopened.table.columnWidth(5) == 140


def test_close_flushes_pending_width_without_wait(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.table.setColumnWidth(2, 420)
    window.close()
    assert not window.column_width_timer.isActive()
    assert load_preferences().column_widths['matches'] == 420


def test_dragging_selection_column_does_not_toggle_file_selection(qtbot, roots, tmp_path):
    from comparador.engine import scan
    from comparador.models import ScanOptions
    folder, _ = roots
    for name in ('first.dat', 'second.dat'):
        (folder / name).write_bytes(b'identical')
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(scan(ScanOptions(folder), cache_path=tmp_path / 'cache.db'))
    window.show()
    selected = {window.visible_keys()[0]}
    window.set_checked(selected)
    header = window.table.horizontalHeader()
    before = header.sectionSize(0)
    qtbot.mouseMove(header.viewport(), QPoint(before - 1, 15))
    qtbot.mousePress(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(before - 1, 15))
    qtbot.mouseMove(header.viewport(), QPoint(before + 35, 15))
    qtbot.mouseRelease(header.viewport(), Qt.MouseButton.LeftButton, pos=QPoint(before + 35, 15))
    assert header.sectionSize(0) > before
    assert window.checked_keys == selected
    qtbot.waitUntil(lambda: not window.jobs and not window.column_width_timer.isActive(), timeout=5000)


def test_width_save_failure_does_not_interrupt_review(qtbot, monkeypatch):
    window = MainWindow()
    qtbot.addWidget(window)
    def fail(*args):
        raise PermissionError('settings unavailable')
    monkeypatch.setattr('comparador.ui.save_preferences', fail)
    window.table.setColumnWidth(1, 345)
    qtbot.waitUntil(lambda: not window.column_width_timer.isActive())
    assert 'settings unavailable' in window.notice.text()
    assert window.table.columnWidth(1) == 345


def test_reset_widths_applies_on_save_and_retains_visible_columns(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.table.setColumnWidth(1, 520)
    original = window.preferences
    dialog = PreferencesDialog(original)
    qtbot.addWidget(dialog)
    dialog.reset_widths.click()
    assert original.column_widths['file'] == 520
    assert dialog.preferences().column_widths == {}
    assert dialog.preferences().visible_columns == original.visible_columns
    window.apply_preferences(dialog.preferences())
    assert window.table.columnWidth(1) == DEFAULT_COLUMN_WIDTHS['file']
    qtbot.waitUntil(lambda: not window.column_width_timer.isActive())


@pytest.mark.parametrize('widths', [[], {'unknown': 100}, {'file': 0}, {'file': 2401}, {'file': True}, {'file': 100.5}])
def test_invalid_width_settings_are_rejected(widths):
    with pytest.raises(ValueError):
        Preferences(column_widths=widths).validate()
