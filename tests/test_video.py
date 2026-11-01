from pathlib import Path
from unittest.mock import patch
import shutil
import threading

import pytest

from comparador.engine import scan
from comparador.models import ScanOptions
from comparador.video import compare_pair, find_similar, fingerprint, probe, thumbnail


@pytest.fixture(scope="module")
def analyzed(media, tmp_path_factory):
    root = tmp_path_factory.mktemp("analysis")
    for name, path in media.items():
        if name != "root":
            shutil.copy2(path, root / path.name)
    return scan(ScanOptions(root, similar=True), cache_path=root.parent / "video-cache.db")


def get(result, name):
    return next(f for f in result.files.values() if Path(f.path).name == name)


def test_transcode_resize_and_trim(analyzed):
    assert analyzed.video_complete
    a = get(analyzed, "original.mp4")
    converted = get(analyzed, "convertido.mkv")
    trimmed = get(analyzed, "recortado.mp4")
    for other in (converted, trimmed):
        match = compare_pair(a, other, 90, 80, threading.Event())
        assert match, f"No se detectó {other.path}"
        assert match.similarity >= 90
        assert match.coverage >= 80
        assert match.spans


def test_odd_second_trim(analyzed):
    assert compare_pair(get(analyzed, "original.mp4"), get(analyzed, "recorte_impar.mp4"), 90, 80, threading.Event())


def test_different_and_black_do_not_match(analyzed):
    a = get(analyzed, "original.mp4")
    for name in ("diferente.mp4", "negro.mp4"):
        assert compare_pair(a, get(analyzed, name), 90, 80, threading.Event()) is None
    black = get(analyzed, "negro.mp4")
    assert not any(h is not None for h in black.fingerprint["hashes"])


def test_threshold_recalculation_does_not_decode(analyzed):
    with patch("comparador.video.run_media", side_effect=AssertionError("No debe decodificar")):
        loose = find_similar(list(analyzed.files.values()), 85, 75, threading.Event())
        strict = find_similar(list(analyzed.files.values()), 99, 100, threading.Event())
    assert len(loose) > len(strict)


def test_shared_intro_and_order_are_not_enough(analyzed):
    import copy
    a = get(analyzed, "original.mp4")
    b = copy.deepcopy(a)
    b.path += ".other"
    b.digest = "other"
    b.fingerprint["hashes"][3:] = get(analyzed, "diferente.mp4").fingerprint["hashes"][3:]
    assert compare_pair(a, b, 90, 80, threading.Event()) is None
    b.fingerprint["hashes"] = list(reversed(a.fingerprint["hashes"]))
    assert compare_pair(a, b, 90, 80, threading.Event()) is None


def test_corrupt_video_not_classified_absent(roots, tmp_path):
    a, b = roots
    (b / "roto.mp4").write_bytes(b"not a video")
    result = scan(ScanOptions(a, b, similar=True), cache_path=tmp_path / "c.db")
    assert not result.video_complete
    assert all(result.classification(k) == "Error or pending" for k in result.files)


def test_thumbnail(media):
    image = thumbnail(media["original"], 4, threading.Event())
    assert image.startswith(b"\xff\xd8")
