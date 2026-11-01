from pathlib import Path
import os
import subprocess

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def isolated_operation_log(tmp_path, monkeypatch):
    monkeypatch.setattr("comparador.operations.data_dir", lambda: tmp_path)
    monkeypatch.setenv("VIDEO_DUPLICATE_FINDER_DATA_DIR",str(tmp_path / 'appdata'))
    (tmp_path / 'appdata').mkdir(exist_ok=True)
    (tmp_path / 'appdata/settings.json').write_text('{"language":"es","theme":"light"}',encoding='utf-8')
    from comparador.i18n import set_language
    set_language('es')


@pytest.fixture
def roots(tmp_path):
    primary, secondary = tmp_path / "Principal", tmp_path / "Secundaria"
    primary.mkdir()
    secondary.mkdir()
    return primary, secondary


@pytest.fixture(scope="session")
def media(tmp_path_factory):
    from comparador.video import binary
    root = tmp_path_factory.mktemp("videos")
    original = root / "original.mp4"
    def ffmpeg(*args):
        subprocess.run([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", *map(str, args)], check=True, capture_output=True)
    # Animated, textured content with moving subject, scene changes and varying lighting.
    ffmpeg("-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=24", "-vf",
           "drawbox=x=40+80*sin(t):y=30:w=30:h=50:color=white:t=fill", "-c:v", "libx264", "-pix_fmt", "yuv420p", original)
    converted = root / "convertido.mkv"
    ffmpeg("-i", original, "-vf", "scale=160:90", "-c:v", "libx264", "-crf", "30", converted)
    trimmed = root / "recortado.mp4"
    ffmpeg("-ss", "2", "-i", original, "-t", "20", "-c:v", "libx264", "-crf", "24", trimmed)
    odd_trim = root / "recorte_impar.mp4"
    ffmpeg("-ss", "1", "-i", original, "-t", "22", "-c:v", "libx264", "-crf", "24", odd_trim)
    different = root / "diferente.mp4"
    ffmpeg("-f", "lavfi", "-i", "life=size=320x180:rate=12:ratio=0.4", "-t", "24", "-c:v", "libx264", different)
    black = root / "negro.mp4"
    ffmpeg("-f", "lavfi", "-i", "color=c=black:size=320x180:rate=12:duration=24", "-c:v", "libx264", black)
    return {"root": root, "original": original, "converted": converted, "trimmed": trimmed, "odd_trim": odd_trim, "different": different, "black": black}
