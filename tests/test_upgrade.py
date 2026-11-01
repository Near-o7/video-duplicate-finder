from pathlib import Path
from unittest.mock import patch
import threading
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QDialog, QComboBox, QPlainTextEdit, QVBoxLayout

from comparador.engine import scan
from comparador.models import ScanOptions, Match
from comparador.operations import plan_actions, execute_actions
from comparador.selection import redundant_keys
from comparador.ui import MainWindow
from comparador.video import fast_fingerprint


def sample(roots, tmp_path):
    a, b = roots
    (a / "referencia.dat").write_bytes(b"same")
    (b / "copia.dat").write_bytes(b"same")
    (b / "nuevo.dat").write_bytes(b"new")
    return scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")


def test_select_all_and_safe_copies_manage_secondary(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.new_scan = True
    window.scan_done(sample(roots, tmp_path))
    assert window.scope_filter.currentIndex() == 2
    assert window.table.rowCount() == 2
    window.select_all_visible()
    assert len(window.selected_keys()) == 2
    assert window.move_button.isEnabled()
    assert window.transfer_button.isEnabled()
    assert window.transfer_button.text() == "Mover a principal"
    window.select_redundant()
    assert len(window.selected_keys()) == 1
    assert window.trash_button.isEnabled()
    assert all(window.result.files[k].root == "secondary" for k in window.selected_keys())
    planned = plan_actions(window.result, window.selected_keys(), "trash")
    assert window.result.files[planned[0].keeper].root == "primary"
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_one_folder_safe_selection_keeps_one(roots, tmp_path):
    a, _ = roots
    for name in ("a", "b", "c"):
        (a / name).write_bytes(b"same")
    result = scan(ScanOptions(a), cache_path=tmp_path / "c.db")
    selected = redundant_keys(result, result.files)
    assert len(selected) == 2
    assert len(plan_actions(result, selected, "trash")) == 2


def test_selection_preserved_across_filters(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(sample(roots, tmp_path))
    window.scope_filter.setCurrentIndex(2)
    window.select_redundant()
    selected = window.selected_keys()
    window.search.setText("nuevo")
    assert window.selected_keys() == selected
    window.clear_selection()
    assert not window.selected_keys()
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_unlock_immediately_updates_primary_actions(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(sample(roots, tmp_path))
    window.scope_filter.setCurrentIndex(1)
    window.select_all_visible()
    assert not window.trash_button.isEnabled()
    window.unlock.setChecked(True)
    assert window.trash_button.isEnabled()
    assert window.transfer_button.text() == "Mover a secundaria"
    window.unlock.setChecked(False)
    assert not window.move_button.isEnabled()
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_popup_theme_remains_legible_after_dark_system_palette(qtbot, qapp):
    dark = QPalette()
    dark.setColor(QPalette.ColorRole.Base, QColor("#161616"))
    dark.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
    qapp.setPalette(dark)
    window = MainWindow()
    qtbot.addWidget(window)
    dialog = QDialog(window)
    layout = QVBoxLayout(dialog)
    combo = QComboBox()
    combo.addItems(["Principal", "Secundaria"])
    layout.addWidget(combo)
    text = QPlainTextEdit("Texto del diálogo")
    layout.addWidget(text)
    dialog.show()
    qtbot.addWidget(dialog)
    assert combo.view().palette().color(QPalette.ColorRole.Base).lightness() > 220
    assert text.palette().color(QPalette.ColorRole.Text).lightness() < 100


def test_fast_sampling_is_bounded_and_seeks(media):
    from comparador.video import probe
    cancel = threading.Event()
    metadata = probe(media["original"], cancel)
    fp = fast_fingerprint(media["original"], metadata, cancel)
    assert len(fp["hashes"]) <= 24
    assert fp["profile"] == "fast"


def test_exact_copies_reuse_decoding(roots, tmp_path, media):
    import shutil
    import comparador.engine as engine
    a, b = roots
    shutil.copy2(media["original"], a / "original.mp4")
    shutil.copy2(media["original"], b / "renombrado.mp4")
    with patch.object(engine, "fast_fingerprint", wraps=engine.fast_fingerprint) as decoder:
        result = scan(ScanOptions(a, b, similar=True), cache_path=tmp_path / "c.db")
    assert result.exact_groups
    assert decoder.call_count == 1


def test_fast_and_full_cache_are_separate(roots, tmp_path, media):
    import shutil
    import comparador.engine as engine
    a, _ = roots
    shutil.copy2(media["original"], a / "original.mp4")
    fast = ScanOptions(a, similar=True)
    full = ScanOptions(a, similar=True, video_profile="full")
    scan(fast, cache_path=tmp_path / "c.db")
    with patch.object(engine, "fingerprint", wraps=engine.fingerprint) as decoder:
        scan(full, cache_path=tmp_path / "c.db")
        assert decoder.call_count == 1
    with patch.object(engine, "fast_fingerprint", side_effect=AssertionError("Debe reutilizar caché")):
        result = scan(fast, cache_path=tmp_path / "c.db")
        assert result.video_complete


def test_batch_visual_review_and_conserved_references(qtbot, roots, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    result = sample(roots, tmp_path)
    primary = next(k for k, f in result.files.items() if f.root == "primary")
    secondary = [k for k, f in result.files.items() if f.root == "secondary"]
    result.exact_groups = []
    result.similar_matches = [Match(primary, k, "similar", 95, 85, [[0, 10, 0, 10]]) for k in secondary]
    window.scan_done(result)
    dialog, combos = window.keeper_dialog(secondary)
    qtbot.addWidget(dialog)
    assert len(combos) == 2
    assert all(combo.currentData() == primary for combo in combos.values())
    assert all(combo.view().palette().color(QPalette.ColorRole.Base).lightness() > 220 for combo in combos.values())
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_full_profile_still_detects_transcode_and_trim(media, tmp_path):
    import shutil
    from comparador.video import compare_pair
    root = tmp_path / "videos"
    root.mkdir()
    for name in ("original", "converted", "odd_trim"):
        shutil.copy2(media[name], root / media[name].name)
    result = scan(ScanOptions(root, similar=True, video_profile="full"), cache_path=tmp_path / "c.db")
    assert result.video_complete
    original = next(f for f in result.files.values() if Path(f.path).name == "original.mp4")
    assert all(compare_pair(original, f, 90, 80, threading.Event()) for f in result.files.values() if f is not original)
