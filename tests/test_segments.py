from pathlib import Path
from random import Random
from unittest.mock import patch
import shutil
import subprocess
import threading

import pytest

from comparador.engine import scan
from comparador.models import Cancelled, FileRecord, ScanOptions, ScanResult
from comparador.preferences_dialog import PreferencesDialog
from comparador.reports import export_csv, export_html
from comparador.segments import compare_segments
from comparador.settings import Preferences, load_preferences, save_preferences
from comparador.ui import MainWindow
from comparador.video import binary, compare_pair, find_similar


def record(tmp_path, name, hashes, step=1):
    return FileRecord(str(tmp_path / name), 'primary', name, 1, 0, 0, 0,
                      metadata={'duration': len(hashes) * step},
                      fingerprint={'step': step, 'hashes': hashes})


def hashes(seed, count):
    rng = Random(seed)
    return [rng.getrandbits(63) for _ in range(count)]


def edited_pair(tmp_path):
    source = hashes(42, 80)
    edited = [h ^ 15 for h in source[:20] + source[30:50] + source[60:]]
    return record(tmp_path, 'source.mp4', source), record(tmp_path, 'edited.mp4', edited)


def test_internal_cuts_and_effects_use_independent_offsets(tmp_path):
    a, b = edited_pair(tmp_path)
    assert compare_pair(a, b, 90, 70, None) is None
    match = compare_segments(a, b, 90, 70, None)
    assert match and match.coverage == 75
    assert len(match.spans) == 3
    assert match.spans == [[0, 20, 0, 20], [30, 50, 20, 40], [60, 80, 40, 60]]
    assert match.similarity == pytest.approx(100 * (1 - 4 / 63))
    assert not match.estimated
    assert compare_segments(a, b, 95, 70, None) is None
    assert compare_segments(a, b, 90, 80, None) is None
    reverse = compare_segments(b, a, 90, 70, None)
    assert reverse.coverage == match.coverage
    assert reverse.spans == [[s[2], s[3], s[0], s[1]] for s in match.spans]


def test_inserted_scenes_and_internal_cuts(tmp_path):
    source = hashes(41, 80)
    edited = source[:20] + hashes(42, 10) + source[30:60] + hashes(43, 10) + source[70:]
    match = compare_segments(record(tmp_path, 'a.mp4', source), record(tmp_path, 'b.mp4', edited), 90, 70, None)
    assert match and match.coverage == 75
    assert len(match.spans) == 3


def test_reordered_scenes_and_unrelated_videos_do_not_pass(tmp_path):
    a, _ = edited_pair(tmp_path)
    for content in (hashes(43, 80), a.fingerprint['hashes'][:5] + hashes(44, 75),
                    list(reversed(a.fingerprint['hashes']))):
        assert compare_segments(a, record(tmp_path, 'other.mp4', content), 90, 50, None) is None


@pytest.mark.parametrize('content', [[None] * 80, [123456] * 80, [123456 ^ (i % 3) for i in range(80)]])
def test_uniform_and_repeated_stills_are_not_evidence(tmp_path, content):
    assert compare_segments(record(tmp_path, 'a.mp4', content), record(tmp_path, 'b.mp4', content), 90, 10, None) is None


def test_repeated_content_cannot_multiply_coverage(tmp_path):
    content = hashes(45, 20)
    a = record(tmp_path, 'a.mp4', content)
    b = record(tmp_path, 'b.mp4', content * 4)
    match = compare_segments(a, b, 90, 10, None)
    assert match and match.coverage == 25
    assert len(match.spans) == 1
    assert compare_segments(a, b, 90, 30, None) is None


def test_loose_threshold_still_requires_sequence_evidence(tmp_path):
    source = hashes(81, 300)
    a = record(tmp_path, 'a.mp4', source)
    different = record(tmp_path, 'different.mp4', hashes(82, 300))
    assert compare_segments(a, different, 50, 10, None) is None
    edited = record(tmp_path, 'edited.mp4', [h ^ ((1 << 20) - 1) for h in source[:100] + source[150:250]])
    match = compare_segments(a, edited, 50, 50, None)
    assert match and match.coverage >= 60


def test_sparse_or_isolated_captures_do_not_form_segments(tmp_path):
    a, b = edited_pair(tmp_path)
    b.fingerprint['estimated'] = True
    assert compare_segments(a, b, 90, 10, None) is None
    b.fingerprint = {'step': 1, 'hashes': [h if i % 3 == 0 else None for i, h in enumerate(a.fingerprint['hashes'])]}
    assert compare_segments(a, b, 90, 10, None) is None


def test_cancel_segments_and_recalculate_without_decoding(tmp_path):
    a, b = edited_pair(tmp_path)
    cancel = threading.Event()
    cancel.set()
    with pytest.raises(Cancelled):
        compare_segments(a, b, 90, 70, cancel)
    with patch('comparador.video.run_media', side_effect=AssertionError('Unexpected decoding')):
        assert len(find_similar([a, b], 90, 70, None, mode='segments')) == 1
        assert not find_similar([a, b], 90, 80, None, mode='segments')


def test_preferences_and_scan_limits_are_profile_specific(tmp_path):
    preferences = Preferences(similar=True, video_profile='segments', coverage=10)
    save_preferences(preferences, tmp_path / 'preferences.json')
    assert load_preferences(tmp_path / 'preferences.json') == preferences
    ScanOptions(tmp_path, similar=True, video_profile='segments', coverage=10).validate()
    for profile in ('fast', 'full'):
        with pytest.raises(ValueError):
            ScanOptions(tmp_path, video_profile=profile, coverage=10).validate()
        with pytest.raises(ValueError):
            Preferences(video_profile=profile, coverage=10).validate()


def test_main_and_settings_offer_segment_profile(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.primary_path.setText(str(tmp_path))
    window.analysis_mode.setCurrentIndex(1)
    window.video_profile.setCurrentIndex(window.video_profile.findData('segments'))
    window.coverage.setValue(10)
    assert window.options().video_profile == 'segments'
    assert window.options().coverage == 10
    assert not window.profile_note.isHidden()
    dialog = PreferencesDialog(Preferences(similar=True, video_profile='segments', coverage=20))
    qtbot.addWidget(dialog)
    assert dialog.preferences().video_profile == 'segments'
    assert dialog.preferences().coverage == 20
    dialog.profile.setCurrentIndex(dialog.profile.findData('full'))
    assert dialog.coverage.minimum() == 50


def test_apply_switches_full_to_segments_without_decoding(qtbot, tmp_path, monkeypatch):
    a, b = edited_pair(tmp_path)
    options = ScanOptions(tmp_path, similar=True, video_profile='full')
    result = ScanResult(options, files={a.key: a, b.key: b}, exact_complete=True, video_complete=True)
    window = MainWindow()
    qtbot.addWidget(window)
    monkeypatch.setattr(window, 'load_thumbnails', lambda *args: None)
    window.scan_done(result)
    window.analysis_mode.setCurrentIndex(1)
    window.video_profile.setCurrentIndex(window.video_profile.findData('segments'))
    window.coverage.setValue(70)
    with patch('comparador.video.run_media', side_effect=AssertionError('Unexpected decoding')):
        window.recalculate_matches()
        qtbot.waitUntil(lambda: not window.jobs, timeout=5000)
    assert result.options.video_profile == 'segments'
    assert len(result.similar_matches) == 1


def test_apply_requires_dense_samples_after_quick_scan(qtbot, tmp_path):
    window = MainWindow()
    qtbot.addWidget(window)
    window.result = ScanResult(ScanOptions(tmp_path, similar=True, video_profile='fast'))
    window.video_profile.setCurrentIndex(window.video_profile.findData('segments'))
    window.recalculate_matches()
    assert not window.jobs
    assert 'nuevo análisis' in window.notice.text()
    assert window.result.options.video_profile == 'fast'


def test_real_cut_video_and_full_cache_reuse(media, tmp_path):
    root = tmp_path / 'videos'
    root.mkdir()
    shutil.copy2(media['original'], root / 'source.mp4')
    subprocess.run([binary('ffmpeg'), '-v', 'error', '-nostdin', '-i', str(media['original']), '-vf',
                    "select='lt(t,6)+gte(t,8)*lt(t,14)+gte(t,16)',setpts=N/FRAME_RATE/TB,eq=brightness=0.015:saturation=0.8",
                    '-an', '-c:v', 'libx264', '-crf', '27', str(root / 'edited.mp4')], check=True, capture_output=True)
    options = ScanOptions(root, similar=True, video_profile='full', similarity=85, coverage=60)
    initial = scan(options, cache_path=tmp_path / 'cache.db')
    assert initial.video_complete
    options = ScanOptions(root, similar=True, video_profile='segments', similarity=85, coverage=60)
    with patch('comparador.engine.fingerprint', side_effect=AssertionError('Must reuse full fingerprints')):
        result = scan(options, cache_path=tmp_path / 'cache.db')
    assert result.video_complete
    assert len(result.similar_matches) == 1
    assert len(result.similar_matches[0].spans) >= 2
    export_html(result, tmp_path / 'report.html')
    export_csv(result, tmp_path / 'report.csv')
    assert 'segments' in (tmp_path / 'report.html').read_text(encoding='utf-8')
    assert 'cortes internos' in (tmp_path / 'report.csv').read_text(encoding='utf-8-sig')
