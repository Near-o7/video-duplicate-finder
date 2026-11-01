from dataclasses import replace

import pytest
from PySide6.QtCore import Qt

from comparador.engine import scan
from comparador.models import ScanOptions
from comparador.settings import Preferences, load_preferences, save_preferences
from comparador.ui import MainWindow


def workspace(qtbot, roots, tmp_path, position='right', size=(1440, 900)):
    folder, _ = roots
    for index in range(60):
        (folder / f'Copy {index:02d}.dat').write_bytes(b'same contents')
    result = scan(ScanOptions(folder), cache_path=tmp_path / 'cache.db')
    window = MainWindow()
    qtbot.addWidget(window)
    window.apply_preferences(replace(window.preferences, comparison_position=position))
    window.resize(*size)
    window.new_scan = True
    window.scan_done(result)
    window._set_busy(False)
    window.show()
    qtbot.waitUntil(lambda: window.comparison_sized)
    return window


@pytest.mark.parametrize('size,minimum', [((1920, 1020), 20), ((1440, 900), 17), ((1280, 720), 11)])
def test_side_comparison_leaves_room_for_many_rows(qtbot, roots, tmp_path, size, minimum):
    window = workspace(qtbot, roots, tmp_path, size=size)
    assert window.table.rowCount() == 60
    visible_rows = window.table.viewport().height() // window.table.verticalHeader().defaultSectionSize()
    assert visible_rows >= minimum
    assert not window.preview_scroll.isHidden()
    assert window.notice.isHidden() and window.progress_label.isHidden()
    qtbot.mouseClick(window.scan_details_button, Qt.MouseButton.LeftButton)
    assert not window.notice.isHidden()
    qtbot.mouseClick(window.scan_details_button, Qt.MouseButton.LeftButton)
    assert window.notice.isHidden()
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


@pytest.mark.parametrize('button', ['keep', 'remove'])
def test_preview_decision_returns_arrow_navigation_to_table(qtbot, roots, tmp_path, button):
    window = workspace(qtbot, roots, tmp_path)
    window.table.sortItems(1, Qt.SortOrder.AscendingOrder)
    window.table.selectRow(10)
    qtbot.mouseClick(getattr(window.left_preview, button), Qt.MouseButton.LeftButton)
    assert window.table.hasFocus()
    keys, keepers = set(window.checked_keys), dict(window.preferred_keepers)
    current = window.current_key
    qtbot.keyClick(window.table, Qt.Key.Key_Down)
    assert window.current_key != current
    assert window.checked_keys == keys and window.preferred_keepers == keepers
    qtbot.keyClick(window.table, Qt.Key.Key_Up)
    assert window.current_key == current
    assert window.checked_keys == keys
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_resized_splitter_is_not_reset_by_row_changes(qtbot, roots, tmp_path):
    window = workspace(qtbot, roots, tmp_path)
    window.results_split.setSizes([900, 450])
    sizes = window.results_split.sizes()
    window.table.selectRow(8)
    qtbot.wait(20)
    assert window.results_split.sizes() == sizes
    window.toggle_comparison()
    window.toggle_comparison()
    qtbot.wait(20)
    assert abs(window.results_split.sizes()[1] - sizes[1]) <= 10
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_below_layout_and_active_review_survive_settings(qtbot, roots, tmp_path):
    window = workspace(qtbot, roots, tmp_path)
    window.table.selectRow(7)
    window.choose_preview(True)
    key, selected = window.current_key, set(window.checked_keys)
    updated = replace(window.preferences, comparison_position='below')
    save_preferences(updated, tmp_path / 'preferences.json')
    assert load_preferences(tmp_path / 'preferences.json').comparison_position == 'below'
    window.apply_preferences(updated)
    assert window.results_split.orientation() == Qt.Orientation.Vertical
    assert window.current_key == key and window.checked_keys == selected
    assert window.setup_panel.isHidden()
    window.toggle_comparison()
    window.apply_preferences(replace(updated, theme='dark'))
    assert window.preview_scroll.isHidden()
    assert window.comparison_toggle.text() == 'Mostrar comparación'
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_unknown_comparison_position_rejected():
    with pytest.raises(ValueError):
        Preferences(comparison_position='unknown').validate()
