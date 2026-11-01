from pathlib import Path
from unittest.mock import patch
import threading

import pytest

from comparador.engine import scan, hash_file
from comparador.models import ScanOptions, Match
from comparador.operations import plan_actions, execute_actions, verified_move


@pytest.fixture
def duplicates(roots, tmp_path):
    a, b = roots
    (a / "keep.txt").write_bytes(b"same payload")
    (b / "remove.txt").write_bytes(b"same payload")
    return scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")


def by_role(result, role):
    return next(k for k, f in result.files.items() if f.root == role)


def test_primary_and_last_copy_protected(duplicates):
    primary, secondary = by_role(duplicates, "primary"), by_role(duplicates, "secondary")
    with pytest.raises(ValueError, match="protegida"):
        plan_actions(duplicates, [primary], "trash")
    with pytest.raises(ValueError, match="conservar"):
        plan_actions(duplicates, [primary, secondary], "trash", unlocked=True)
    assert plan_actions(duplicates, [primary], "trash", unlocked=True)[0].keeper == secondary


def test_deleted_or_changed_keeper_blocks(duplicates):
    primary, secondary = by_role(duplicates, "primary"), by_role(duplicates, "secondary")
    actions = plan_actions(duplicates, [secondary], "trash")
    Path(duplicates.files[primary].path).write_bytes(b"changed")
    calls = []
    result = execute_actions(duplicates, actions, "trash", trash_func=calls.append)
    assert not result[0]["ok"]
    assert not calls
    assert Path(duplicates.files[secondary].path).exists()


def test_same_metadata_content_change_rechecked(duplicates):
    import os
    secondary = by_role(duplicates, "secondary")
    record = duplicates.files[secondary]
    path = Path(record.path)
    actions = plan_actions(duplicates, [secondary], "trash")
    old = path.stat()
    path.write_bytes(b"evil payload")
    os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    calls = []
    outcomes = execute_actions(duplicates, actions, "trash", trash_func=calls.append)
    assert not calls
    assert not outcomes[0]["ok"]


def test_move_preserves_subfolders_and_handles_collisions(duplicates, tmp_path):
    secondary = by_role(duplicates, "secondary")
    dest = tmp_path / "revision"
    dest.mkdir()
    (dest / "remove.txt").write_bytes(b"do not overwrite")
    actions = plan_actions(duplicates, [secondary], "move", dest)
    assert actions[0].collision
    assert actions[0].destination.endswith("remove (1).txt")
    outcomes = execute_actions(duplicates, actions, "move", log_path=tmp_path / "ops.jsonl")
    assert outcomes[0]["ok"]
    assert (dest / "remove.txt").read_bytes() == b"do not overwrite"
    assert (dest / "remove (1).txt").read_bytes() == b"same payload"


def test_trash_failure_never_permanently_deletes(duplicates, tmp_path):
    secondary = by_role(duplicates, "secondary")
    actions = plan_actions(duplicates, [secondary], "trash")
    def failing(_):
        raise OSError("Papelera no disponible")
    outcome = execute_actions(duplicates, actions, "trash", trash_func=failing, log_path=tmp_path / "ops.jsonl")
    assert not outcome[0]["ok"]
    assert Path(duplicates.files[secondary].path).exists()


def test_partial_batch_failure_keeps_other_results(roots, tmp_path):
    a, b = roots
    for name in ("keep", "one", "two"):
        ((a if name == "keep" else b) / name).write_bytes(b"same")
    result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    keys = [k for k, f in result.files.items() if f.root == "secondary"]
    actions = plan_actions(result, keys, "trash")
    called = []
    def fake_trash(path):
        called.append(path)
        if len(called) == 1:
            raise PermissionError("Bloqueado")
        Path(path).unlink()
    outcomes = execute_actions(result, actions, "trash", trash_func=fake_trash, log_path=tmp_path / "ops.jsonl")
    assert [o["ok"] for o in outcomes] == [False, True]


def test_visual_candidate_needs_explicit_keeper(roots, tmp_path):
    a, b = roots
    (a / "keep").write_bytes(b"a")
    (b / "candidate").write_bytes(b"bb")
    result = scan(ScanOptions(a, b), cache_path=tmp_path / "c.db")
    primary, secondary = by_role(result, "primary"), by_role(result, "secondary")
    result.similar_matches = [Match(primary, secondary, "similar", 95, 90)]
    with pytest.raises(ValueError):
        plan_actions(result, [secondary], "trash")
    assert plan_actions(result, [secondary], "trash", keepers={secondary: primary})


def test_move_does_not_overwrite_late_collision(tmp_path):
    source, dest = tmp_path / "a", tmp_path / "b"
    source.write_bytes(b"source")
    dest.write_bytes(b"target")
    with pytest.raises(FileExistsError):
        verified_move(source, dest, hash_file(source))
    assert source.read_bytes() == b"source"
    assert dest.read_bytes() == b"target"


def test_cross_device_copy_verified_before_source_removal(tmp_path):
    source, dest = tmp_path / "a", tmp_path / "b"
    source.write_bytes(b"data" * 10000)
    import comparador.operations as ops
    original_stat = Path.stat
    class FakeStat:
        st_dev = -999
    def stat(path, *args, **kwargs):
        if path == source:
            return FakeStat()
        return original_stat(path, *args, **kwargs)
    # Isolate only the device comparison; copy metadata is separately exercised by normal moves.
    with patch.object(Path, "stat", stat), patch.object(ops.shutil, "copystat"):
        verified_move(source, dest, hash_file(source))
    assert not source.exists()
    assert dest.read_bytes() == b"data" * 10000


def test_cross_device_verification_failure_preserves_source(tmp_path):
    source, dest = tmp_path / "a", tmp_path / "b"
    source.write_bytes(b"data")
    original_stat = Path.stat
    class FakeStat:
        st_dev = -999
    def stat(path, *args, **kwargs):
        return FakeStat() if path == source else original_stat(path, *args, **kwargs)
    with patch.object(Path, "stat", stat):
        with pytest.raises(OSError, match="verificación"):
            verified_move(source, dest, "incorrect")
    assert source.exists()
    assert not dest.exists()
    assert not list(tmp_path.glob("*.partial"))
