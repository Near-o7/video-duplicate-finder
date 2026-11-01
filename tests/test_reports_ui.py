from pathlib import Path

from PySide6.QtCore import Qt

from comparador.engine import scan
from comparador.models import ScanOptions
from comparador.reports import export_csv, export_html
from comparador.ui import MainWindow


def sample(roots, tmp_path):
    a, b = roots
    (a / "Película á &.dat").write_bytes(b"same")
    (b / "copia.dat").write_bytes(b"same")
    (b / "nuevo.dat").write_bytes(b"other")
    return scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")


def test_reports_include_thresholds_and_escape(roots, tmp_path):
    result = sample(roots, tmp_path)
    result.errors.append("Error de ejemplo: & < >")
    export_csv(result, tmp_path / "out.csv")
    export_html(result, tmp_path / "out.html")
    assert (tmp_path / "out.csv").read_bytes().startswith(b"\xef\xbb\xbf")
    html = (tmp_path / "out.html").read_text(encoding="utf-8")
    assert "&amp; &lt;" in html
    assert "Sin coincidencias detectadas" in html
    assert "90.0%" in html


def test_gui_filter_selection_and_protection(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(sample(roots, tmp_path))
    assert window.table.rowCount() == 3
    assert not window.selected_keys()
    assert not window.unlock.isChecked()
    window.table.item(0, 0).setCheckState(Qt.CheckState.Checked)
    assert len(window.selected_keys()) == 1
    first_key = window.table.item(0, 0).data(Qt.ItemDataRole.UserRole)
    assert window.trash_button.isEnabled() == (window.result.files[first_key].root == "secondary")
    window.clear_selection()
    assert not window.selected_keys()
    window.view_filter.setCurrentIndex(3)
    assert window.table.rowCount() == 1
    assert window.table.item(0, 1).text().startswith("nuevo")
    window.view_filter.setCurrentIndex(5)
    assert window.table.rowCount() == 0
    window.view_filter.setCurrentIndex(0)
    window.search.setText("copia")
    assert window.table.rowCount() == 1
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_worker_scan_keeps_ui_responsive(qtbot, roots, tmp_path):
    a, b = roots
    (a / "one").write_bytes(b"same")
    (b / "two").write_bytes(b"same")
    window = MainWindow()
    qtbot.addWidget(window)
    window.primary_path.setText(str(a))
    window.secondary_path.setText(str(b))
    window.folder_mode.setCurrentIndex(1)
    window.start_scan()
    assert window.worker is not None
    assert not window.scan_button.isEnabled()
    qtbot.waitUntil(lambda: window.worker is None, timeout=10000)
    assert len(window.result.exact_groups) == 1
    assert window.scan_button.isEnabled()
    assert window.progress.value() == 100
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)
