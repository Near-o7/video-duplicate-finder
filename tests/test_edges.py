from pathlib import Path
from unittest.mock import patch
import os
import threading
import time

import pytest

from comparador.engine import scan
from comparador.models import ScanOptions, Cancelled, FileRecord, Match, duration_text
from comparador.operations import plan_actions, execute_actions
from comparador.reports import export_csv, report_rows
from comparador.video import run_media, binary


def test_directory_read_failure_never_claims_absence(roots, tmp_path):
    a, b = roots
    (b / "solo.txt").write_text("b")
    real_scandir = os.scandir
    def guarded(path):
        if Path(path) == a:
            raise PermissionError("Acceso denegado a principal")
        return real_scandir(path)
    with patch("comparador.engine.os.scandir", guarded):
        result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    assert result.errors
    assert not result.exact_complete
    assert all(result.classification(k) == "Error or pending" for k in result.files)


def test_long_paths_and_unicode(roots, tmp_path):
    a, b = roots
    nested = a
    for _ in range(5):
        nested /= "Carpeta con tildes áéíóú " + "x" * 30
    try:
        nested.mkdir(parents=True)
        (nested / "película.txt").write_bytes(b"same")
    except OSError:
        pytest.skip("El sistema no tiene habilitadas rutas largas para Python")
    (b / "copia.txt").write_bytes(b"same")
    result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    assert result.exact_complete
    assert len(result.exact_groups) == 1
    assert len(str(nested)) > 260


def test_directory_symlink_not_followed(roots, tmp_path):
    a, b = roots
    (b / "outside.txt").write_bytes(b"other root")
    try:
        os.symlink(b, a / "link", target_is_directory=True)
    except OSError:
        pytest.skip("Windows no permite crear enlaces simbólicos en esta sesión")
    result = scan(ScanOptions(a), cache_path=tmp_path / "c.db")
    assert not result.files


def test_cancel_stops_ffmpeg_and_returns_promptly():
    cancel = threading.Event()
    timer = threading.Timer(0.3, cancel.set)
    timer.start()
    start = time.monotonic()
    try:
        with pytest.raises(Cancelled):
            run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-re", "-f", "lavfi", "-i",
                       "testsrc2=size=32x32:rate=1", "-f", "null", "-"], cancel)
        assert time.monotonic() - start < 3
    finally:
        timer.cancel()


def test_cancelled_batch_preserves_unprocessed_files(roots, tmp_path):
    a, b = roots
    (a / "keeper").write_bytes(b"same")
    (b / "one").write_bytes(b"same")
    (b / "two").write_bytes(b"same")
    result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    keys = [k for k, f in result.files.items() if f.root == "secondary"]
    actions = plan_actions(result, keys, "trash")
    cancel = threading.Event()
    def fake_trash(path):
        Path(path).unlink()
        cancel.set()
    with pytest.raises(Cancelled):
        execute_actions(result, actions, "trash", cancel, trash_func=fake_trash, log_path=tmp_path / "actions.jsonl")
    assert not result.files[keys[0]].active
    assert Path(result.files[keys[1]].path).exists()
    assert (a / "keeper").exists()


def test_moving_nested_files_keeps_relative_structure(roots, tmp_path):
    a, _ = roots
    (a / "sub").mkdir()
    (a / "sub" / "one.txt").write_text("one")
    dest = tmp_path / "review"
    dest.mkdir()
    result = scan(ScanOptions(a), cache_path=tmp_path / "c.db")
    actions = plan_actions(result, list(result.files), "move", dest)
    outcomes = execute_actions(result, actions, "move", log_path=tmp_path / "actions.jsonl")
    assert outcomes[0]["ok"]
    assert (dest / "sub" / "one.txt").read_text() == "one"


def test_report_orients_visual_spans_and_formats_zero(roots, tmp_path):
    a, b = roots
    (a / "one").write_text("a")
    (b / "two").write_text("bb")
    result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    keys = list(result.files)
    result.similar_matches = [Match(keys[0], keys[1], "similar", 95, 85, [[0, 10, 2, 12]])]
    rows = list(report_rows(result))
    assert "00:00:00 to 00:00:10 / 00:00:02 to 00:00:12" in rows[0][9]
    assert "00:00:02 to 00:00:12 / 00:00:00 to 00:00:10" in rows[1][9]
    assert duration_text(0) == "00:00:00"
