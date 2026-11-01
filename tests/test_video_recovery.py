import json
import threading
from unittest.mock import patch

import pytest
import av

from comparador.engine import scan
from comparador.models import Cancelled, ScanOptions
from comparador.video import fast_fingerprint, probe, _fast_ffmpeg, run_media, binary


@pytest.mark.parametrize('failure', [EOFError('seek failed'), av.DecoderNotFoundError(1, 'decoder unavailable'), av.error.NotImplementedError(1, 'seek not supported')])
def test_failed_seek_recovers_with_same_grid(media, failure):
    cancel = threading.Event()
    metadata = probe(media['original'], cancel)
    normal = fast_fingerprint(media['original'], metadata, cancel)
    with patch('comparador.video._fast_pyav', side_effect=failure):
        recovered = fast_fingerprint(media['original'], metadata, cancel)
    assert recovered['reader'] == 'ffmpeg'
    assert recovered['step'] == normal['step']
    assert len(recovered['hashes']) == len(normal['hashes'])
    distances = [(a ^ b).bit_count() for a, b in zip(recovered['hashes'], normal['hashes']) if a is not None and b is not None]
    assert distances and max(distances) <= 6


def test_cancellation_never_starts_alternative_reader():
    with patch('comparador.video._fast_pyav', side_effect=Cancelled()), patch('comparador.video._fast_ffmpeg') as alternative:
        with pytest.raises(Cancelled):
            fast_fingerprint('unused', {}, threading.Event())
        alternative.assert_not_called()


def test_incomplete_alternative_samples_remain_error():
    with patch('comparador.video._fast_pyav', side_effect=EOFError('bad seek')), patch('comparador.video.run_media', return_value=b''):
        with pytest.raises(ValueError, match='bad seek'):
            fast_fingerprint('unused', {'duration': 10}, threading.Event())


def test_alternative_reader_has_total_deadline():
    with patch('comparador.video.time.monotonic', side_effect=[0, 46]), patch('comparador.video.run_media') as reader:
        with pytest.raises(ValueError):
            _fast_ffmpeg('unused', {'duration': 10}, threading.Event())
        reader.assert_not_called()


@pytest.mark.parametrize('stream_duration,container_duration,expected', [('N/A', '12', 12), ('10', '20', 10), ('8', 'N/A', 8)])
def test_valid_duration_and_non_cover_stream(stream_duration, container_duration, expected):
    payload = {'format': {'duration': container_duration}, 'streams': [
        {'index': 0, 'codec_type': 'video', 'disposition': {'attached_pic': 1}},
        {'index': 2, 'codec_type': 'video', 'duration': stream_duration, 'width': 320, 'height': 180}]}
    with patch('comparador.video.run_media', return_value=json.dumps(payload).encode()):
        metadata = probe('unused', threading.Event())
    assert metadata['duration'] == expected
    assert metadata['video_stream_index'] == 2


def test_actual_embedded_cover_does_not_replace_video(media, tmp_path):
    cancel = threading.Event()
    cover = tmp_path / 'cover.jpg'
    output = tmp_path / 'with-cover.mp4'
    run_media([binary('ffmpeg'), '-v', 'error', '-y', '-i', str(media['original']), '-frames:v', '1', str(cover)], cancel)
    run_media([binary('ffmpeg'), '-v', 'error', '-y', '-i', str(cover), '-i', str(media['original']),
               '-map', '0:v', '-map', '1:v', '-c', 'copy', '-disposition:v:0', 'attached_pic', str(output)], cancel)
    metadata = probe(output, cancel)
    result = fast_fingerprint(output, metadata, cancel)
    assert len(result['hashes']) >= 3
    assert len(set(result['hashes'])) > 1


def test_failed_video_does_not_label_successful_file_as_read_error(roots, tmp_path, media, qtbot):
    import shutil
    primary, secondary = roots
    (primary / 'damaged.mp4').write_bytes(b'not a video')
    shutil.copy2(media['original'], secondary / 'valid.mp4')
    result = scan(ScanOptions(primary, secondary, similar=True), cache_path=tmp_path / 'cache.db')
    damaged = next(k for k, f in result.files.items() if f.relative == 'damaged.mp4')
    valid = next(k for k, f in result.files.items() if f.relative == 'valid.mp4')
    assert result.display_status(damaged) == 'Video read error'
    assert result.display_status(valid) == 'Comparison incomplete'
    assert not result.files[valid].video_error
    assert result.classification(valid) == 'Error or pending'
    from comparador.ui import MainWindow
    from comparador.reports import report_rows
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(result)
    statuses = {window.table.item(row, 7).text() for row in range(window.table.rowCount())}
    assert statuses == {'Error al leer el video', 'Comparación incompleta'}
    assert {row[2] for row in report_rows(result)} == statuses
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_scan_recovers_and_reuses_alternative_fingerprints(roots, tmp_path, media):
    import shutil
    folder, _ = roots
    shutil.copy2(media['original'], folder / 'valid.mp4')
    options = ScanOptions(folder, similar=True)
    with patch('comparador.video._fast_pyav', side_effect=EOFError('bad seek')):
        result = scan(options, cache_path=tmp_path / 'cache.db')
    assert result.video_complete
    with patch('comparador.engine.fast_fingerprint', side_effect=AssertionError('must reuse cache')):
        assert scan(options, cache_path=tmp_path / 'cache.db').video_complete
