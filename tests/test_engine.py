from pathlib import Path
import os
import shutil
import threading
from unittest.mock import patch

import pytest

from comparador.engine import scan, hash_file
from comparador.models import ScanOptions, Cancelled
from comparador.cache import Cache


def test_exact_two_folders_and_internal_groups(roots, tmp_path):
    a, b = roots
    (a / "subcarpeta").mkdir()
    (a / "subcarpeta" / "película.dat").write_bytes(b"same video" * 100)
    (a / "copia renombrada.bin").write_bytes(b"same video" * 100)
    (b / "otro nombre.xyz").write_bytes(b"same video" * 100)
    (b / "nuevo.dat").write_bytes(b"different!" * 100)
    (b / "vacío.txt").write_bytes(b"")
    result = scan(ScanOptions(a, b), cache_path=tmp_path / "cache.db")
    assert result.exact_complete
    assert len(result.exact_groups) == 1
    assert len(result.exact_groups[0]) == 3
    secondary = {Path(f.path).name: result.classification(k) for k, f in result.files.items() if f.root == "secondary"}
    assert secondary == {"otro nombre.xyz": "Exact copy", "nuevo.dat": "No matches detected", "vacío.txt": "No matches detected"}


def test_same_size_and_partial_hash_do_not_prove_equality(roots, tmp_path):
    a, _ = roots
    payload = bytearray(b"a" * 400000)
    (a / "uno.dat").write_bytes(payload)
    payload[100000] = 98  # Outside the three partial-read regions.
    (a / "dos.dat").write_bytes(payload)
    result = scan(ScanOptions(a), cache_path=tmp_path / "cache.db")
    assert not result.exact_groups
    assert all(f.digest for f in result.files.values())


def test_recursion_filter_and_overlapping_roots(roots, tmp_path):
    a, b = roots
    (a / "sub").mkdir()
    (a / "sub" / "uno.txt").write_text("a")
    (a / "dos.txt").write_text("a")
    assert len(scan(ScanOptions(a, recursive=False), cache_path=tmp_path / "c.db").files) == 1
    assert not scan(ScanOptions(a, videos_only=True), cache_path=tmp_path / "c.db").files
    with pytest.raises(ValueError):
        ScanOptions(a, a / "sub").validate()
    with pytest.raises(ValueError):
        ScanOptions(a, a).validate()


def test_cancelled_scan_never_claims_absence(roots, tmp_path):
    a, b = roots
    (b / "a.txt").write_text("a")
    cancel = threading.Event()
    def progress(*args):
        cancel.set()
    result = scan(ScanOptions(a, b), cancel, progress, tmp_path / "c.db")
    assert result.cancelled
    assert not result.exact_complete
    assert all(result.classification(k) == "Error or pending" for k in result.files)


def test_permission_and_mutation_are_incomplete(roots, tmp_path):
    a, b = roots
    (a / "a.txt").write_bytes(b"same")
    (b / "b.txt").write_bytes(b"same")
    with patch("comparador.engine.partial_hash", side_effect=PermissionError("Sin permiso")):
        result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    assert not result.exact_complete
    assert all(result.classification(k) == "Error or pending" for k in result.files)
    changed = False
    def progress(phase, *_):
        nonlocal changed
        if phase.startswith("Confirmando") and not changed:
            (b / "b.txt").write_bytes(b"changed")
            changed = True
    result = scan(ScanOptions(a, b), progress=progress, cache_path=tmp_path / "c.db")
    assert not result.exact_complete
    assert not result.exact_groups


def test_hardlinks_are_not_independent_copies(roots, tmp_path):
    a, _ = roots
    original = a / "original"
    original.write_bytes(b"content")
    try:
        os.link(original, a / "enlace")
    except OSError:
        pytest.skip("El volumen no admite hard links")
    result = scan(ScanOptions(a), cache_path=tmp_path / "c.db")
    assert not result.exact_groups
    assert any("mismo archivo físico" in f.error for f in result.files.values())


def test_cache_invalidates_change(roots, tmp_path):
    a, _ = roots
    (a / "a").write_bytes(b"aa")
    (a / "b").write_bytes(b"aa")
    first = scan(ScanOptions(a), cache_path=tmp_path / "c.db")
    assert first.exact_groups
    (a / "b").write_bytes(b"bb")
    second = scan(ScanOptions(a), cache_path=tmp_path / "c.db")
    assert not second.exact_groups
