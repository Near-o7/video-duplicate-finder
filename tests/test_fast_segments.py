import copy
import shutil
import subprocess
import threading
from unittest.mock import patch

import pytest

from comparador.engine import scan
from comparador.models import Cancelled, ScanOptions, ScanResult
from comparador.preferences_dialog import PreferencesDialog
from comparador.reports import export_csv, export_html
from comparador.segments import compare_fast_segments
from comparador.selection import redundant_keys
from comparador.settings import Preferences, load_preferences, save_preferences
from comparador.ui import MainWindow
from comparador.video import (binary, fast_segment_fingerprint, find_similar, probe,
                              segment_sample_grid, sparse_segment_fingerprint)
from test_segments import edited_pair, hashes, record


@pytest.mark.parametrize('duration', [0.02, 0.5, 2.9, 3, 160, 161, 1682, 7200, 86400])
def test_grid_is_bounded_and_covers_the_timeline(duration):
    step, targets = segment_sample_grid({'duration': duration})
    assert 1 <= len(targets) <= 160
    assert targets[-1] < duration
    assert duration - targets[-1] <= step + 0.5


def test_fast_runs_preserve_cuts_and_estimate_coverage(tmp_path):
    a, b = edited_pair(tmp_path)
    match = compare_fast_segments(a, b, 90, 70, None)
    assert match.estimated
    assert match.coverage == 75
    assert len(match.spans) == 3
    assert a.fingerprint.get('estimated') is None
    assert not find_similar([a, b], 90, 80, None, mode='segments_fast')
    result = ScanResult(ScanOptions(tmp_path, similar=True, video_profile='segments_fast'),
                        files={a.key: a, b.key: b}, similar_matches=[match])
    assert result.display_status(a.key) == 'Shared video sections'
    assert redundant_keys(result, result.files) == set()
    export_html(result, tmp_path / 'report.html')
    export_csv(result, tmp_path / 'report.csv')
    for name, encoding in [('report.html', 'utf-8'), ('report.csv', 'utf-8-sig')]:
        text = (tmp_path / name).read_text(encoding=encoding)
        assert 'estimados' in text and '160' in text


def test_different_grids_and_repetitions_do_not_inflate_coverage(tmp_path):
    content = hashes(51, 80)
    a = record(tmp_path, 'a.mp4', content * 2)
    b = record(tmp_path, 'b.mp4', (content * 8)[::4], step=4)
    match = compare_fast_segments(a, b, 90, 10, None)
    assert match and match.coverage <= 25
    assert compare_fast_segments(a, b, 90, 30, None) is None


@pytest.mark.parametrize('kind', ['different', 'intro', 'reverse', 'black', 'still'])
def test_no_short_intro_or_static_evidence(tmp_path, kind):
    a, _ = edited_pair(tmp_path)
    content = {'different': hashes(52, 80), 'intro': a.fingerprint['hashes'][:5] + hashes(53, 75),
               'reverse': a.fingerprint['hashes'][::-1], 'black': [None] * 80, 'still': [123456] * 80}[kind]
    b = record(tmp_path, 'b.mp4', content)
    assert compare_fast_segments(a, b, 90, 50, None) is None
    if kind == 'different':
        assert compare_fast_segments(a, b, 50, 10, None) is None


def test_ordinary_quick_grid_is_not_accepted_as_segment_evidence(tmp_path):
    a, b = edited_pair(tmp_path)
    b.fingerprint.update(estimated=True, profile='fast')
    assert compare_fast_segments(a, b, 90, 10, None) is None
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        compare_fast_segments(a, b, 90, 10, cancel)
    with patch('comparador.video._fast_pyav', side_effect=Cancelled()), patch('comparador.video._fast_ffmpeg') as reader:
        with pytest.raises(Cancelled):
            fast_segment_fingerprint('unused', {'duration': 1682}, cancel)
        reader.assert_not_called()


def test_settings_and_ui_allow_fast_segments(qtbot, tmp_path):
    preferences = Preferences(similar=True, video_profile='segments_fast', coverage=10)
    save_preferences(preferences, tmp_path / 'prefs.json')
    assert load_preferences(tmp_path / 'prefs.json') == preferences
    preferences.validate()
    ScanOptions(tmp_path, video_profile='segments_fast', coverage=10).validate()
    window = MainWindow()
    qtbot.addWidget(window)
    window.primary_path.setText(str(tmp_path))
    window.analysis_mode.setCurrentIndex(1)
    window.video_profile.setCurrentIndex(window.video_profile.findData('segments_fast'))
    window.coverage.setValue(10)
    assert window.options().video_profile == 'segments_fast'
    assert window.options().coverage == 10
    assert '160' in window.profile_note.text()
    dialog = PreferencesDialog(preferences)
    qtbot.addWidget(dialog)
    assert dialog.preferences() == preferences
    assert '160' in dialog.profile_note.text()


def test_apply_reuses_dense_fingerprints_but_requires_rescan_to_restore(qtbot, tmp_path):
    a, b = edited_pair(tmp_path)
    result = ScanResult(ScanOptions(tmp_path, similar=True, video_profile='segments'),
                        files={a.key: a, b.key: b}, exact_complete=True, video_complete=True)
    window = MainWindow()
    qtbot.addWidget(window)
    window.result = result
    window.video_profile.setCurrentIndex(window.video_profile.findData('segments_fast'))
    window.coverage.setValue(70)
    with patch('comparador.video.run_media', side_effect=AssertionError('No decoding')):
        window.recalculate_matches()
        qtbot.waitUntil(lambda: not window.jobs, timeout=5000)
    assert result.options.video_profile == 'segments_fast'
    assert len(result.similar_matches) == 1 and result.similar_matches[0].estimated
    window.video_profile.setCurrentIndex(window.video_profile.findData('segments'))
    window.recalculate_matches()
    assert not window.jobs
    assert 'nuevo análisis' in window.notice.text()


def test_real_seek_reader_recovery_and_cache(media, tmp_path):
    root = tmp_path / 'videos'
    root.mkdir()
    shutil.copy2(media['original'], root / 'source.mp4')
    subprocess.run([binary('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(media['original']), '-vf',
                    "select='lt(t,6)+gte(t,8)*lt(t,14)+gte(t,16)',setpts=N/FRAME_RATE/TB,eq=brightness=0.015:saturation=0.8",
                    '-an', '-c:v', 'libx264', '-crf', '27', str(root / 'edited.mp4')], check=True, capture_output=True)
    metadata = probe(media['original'], None)
    normal = fast_segment_fingerprint(media['original'], metadata, None)
    with patch('comparador.video._fast_pyav', side_effect=EOFError('seek failed')):
        recovered = fast_segment_fingerprint(media['original'], metadata, None)
    assert recovered['reader'] == 'ffmpeg'
    assert recovered['profile'] == 'segments_fast'
    assert recovered['step'] == normal['step']
    assert len(recovered['hashes']) == len(normal['hashes'])
    assert max((a ^ b).bit_count() for a, b in zip(normal['hashes'], recovered['hashes']) if a is not None and b is not None) <= 6
    options = ScanOptions(root, similar=True, video_profile='segments_fast', similarity=85, coverage=60)
    result = scan(options, cache_path=tmp_path / 'cache.db')
    assert result.video_complete
    assert len(result.similar_matches) == 1
    assert result.similar_matches[0].estimated
    assert len(result.similar_matches[0].spans) >= 2
    with patch('comparador.engine.fast_segment_fingerprint', side_effect=AssertionError('Must reuse cache')):
        assert scan(options, cache_path=tmp_path / 'cache.db').video_complete
    options.video_profile = 'segments'
    with patch('comparador.engine.fingerprint', wraps=__import__('comparador.video', fromlist=['fingerprint']).fingerprint) as reader:
        assert scan(options, cache_path=tmp_path / 'cache.db').video_complete
        assert reader.call_count == 2
    # A dense cache can supply the quick segment grid without decoding again.
    options.video_profile = 'segments_fast'
    with patch('comparador.engine.fast_segment_fingerprint', side_effect=AssertionError('No decoding')):
        assert scan(options, cache_path=tmp_path / 'cache.db').video_complete


def test_dense_cache_supplies_quick_segments_without_reading_video(media, tmp_path):
    root = tmp_path / 'videos'
    root.mkdir()
    shutil.copy2(media['original'], root / 'source.mp4')
    options = ScanOptions(root, similar=True, video_profile='segments')
    first = scan(options, cache_path=tmp_path / 'dense.db')
    assert first.video_complete
    options.video_profile = 'segments_fast'
    with patch('comparador.engine.fast_segment_fingerprint', side_effect=AssertionError('No seeking')), \
            patch('comparador.engine.fingerprint', side_effect=AssertionError('No full decoding')):
        result = scan(options, cache_path=tmp_path / 'dense.db')
    assert result.video_complete
    assert next(iter(result.files.values())).fingerprint['profile'] == 'segments_fast'


def test_dense_downsampling_is_bounded_and_does_not_change_source():
    dense = {'step': 1, 'hashes': list(range(1682))}
    original = copy.deepcopy(dense)
    sparse = sparse_segment_fingerprint(dense, {'duration': 1682})
    assert len(sparse['hashes']) <= 160 and sparse['step'] == 16
    assert dense == original
    assert sparse['estimated']


def test_seek_deadline_does_not_retry_after_budget_expires():
    with patch('comparador.video._fast_pyav', side_effect=ValueError('timeout')), \
            patch('comparador.video.time.monotonic', side_effect=[0, 61, 61]), \
            patch('comparador.video.run_media') as reader:
        with pytest.raises(ValueError):
            fast_segment_fingerprint('unused', {'duration': 1682}, None)
        reader.assert_not_called()
