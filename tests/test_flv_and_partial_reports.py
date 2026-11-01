from pathlib import Path
import threading

from comparador.engine import scan
from comparador.models import ScanOptions
from comparador.video import binary, run_media, probe, fast_fingerprint, fingerprint, thumbnail, media_input_options
from comparador.reports import report_rows, export_html, export_csv


def test_renamed_flv_with_bad_previous_tag_sizes_can_be_analyzed(tmp_path, media):
    cancel = threading.Event()
    source = tmp_path / 'generated.flv'
    run_media([binary('ffmpeg'), '-v', 'error', '-y', '-i', str(media['original']), '-c:v', 'flv', '-an', '-f', 'flv', str(source)], cancel)
    raw = bytearray(source.read_bytes())
    offset = int.from_bytes(raw[5:9], 'big')
    count = 0
    while offset + 15 < len(raw):
        size = int.from_bytes(raw[offset + 5:offset + 8], 'big')
        raw[offset:offset + 4] = b'\xff\xff\xff\xff'
        offset += 15 + size
        count += 1
    assert count > 20
    video = tmp_path / 'renamed.mp4'
    video.write_bytes(raw)
    assert media_input_options(video) == ['-flv_ignore_prevtag', '1']
    metadata = probe(video, cancel)
    quick = fast_fingerprint(video, metadata, cancel)
    full = fingerprint(video, metadata, cancel)
    assert len(quick['hashes']) >= 3 and len(full['hashes']) >= 20
    assert thumbnail(video, 8, cancel).startswith(b'\xff\xd8')
    assert video.read_bytes() == raw
    assert media_input_options(media['original']) == []


def test_readable_videos_and_nonvideos_have_distinct_partial_statuses(roots, tmp_path, media):
    import shutil
    folder, _ = roots
    (folder / 'unreadable.mp4').write_bytes(b'not a video')
    (folder / 'notes.txt').write_text('only text', encoding='utf-8')
    shutil.copy2(media['original'], folder / 'readable.mp4')
    result = scan(ScanOptions(folder, similar=True), cache_path=tmp_path / 'cache.db')
    keys = {Path(f.path).name: key for key, f in result.files.items()}
    assert result.display_status(keys['readable.mp4']) == 'No matches (partial comparison)'
    assert result.classification(keys['readable.mp4']) == 'Error or pending'
    assert result.classification(keys['notes.txt']) == 'No matches detected'
    assert result.display_status(keys['unreadable.mp4']) == 'Video read error'
    rows = {Path(row[0]).name: row for row in report_rows(result)}
    assert not rows['readable.mp4'][10] and rows['readable.mp4'][11]
    assert rows['unreadable.mp4'][10] and not rows['unreadable.mp4'][11]
    export_html(result, tmp_path / 'report.html')
    export_csv(result, tmp_path / 'report.csv')
    assert 'Notas de comparación' in (tmp_path / 'report.html').read_text(encoding='utf-8')
    result.cancelled = True
    assert result.display_status(keys['readable.mp4']) == 'Comparison incomplete'
