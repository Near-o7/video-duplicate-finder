from pathlib import Path
import shutil

from comparador.engine import scan
from comparador.models import ScanOptions
from comparador.i18n import tr
from comparador.reports import report_rows
from comparador.ui import MainWindow


def completed_with_unrelated_failures(roots, tmp_path, media):
    primary, secondary = roots
    shutil.copy2(media['original'], primary / 'reference.mp4')
    shutil.copy2(media['different'], secondary / 'new.mp4')
    (secondary / 'damaged.mp4').write_bytes(b'not a video')
    removed = primary / 'removed.jpeg'
    removed.write_bytes(b'generated image fixture')
    def progress(phase, *_):
        if phase == tr('Analyzing video content') and removed.exists():
            removed.unlink()
    result = scan(ScanOptions(primary, secondary, similar=True), progress=progress, cache_path=tmp_path / 'cache.db')
    keys = {Path(f.path).name: key for key, f in result.files.items()}
    return result, keys


def test_secondary_absence_uses_primary_references_despite_other_failures(roots, tmp_path, media, qtbot):
    result, keys = completed_with_unrelated_failures(roots, tmp_path, media)
    assert result.comparison_finished
    assert not result.exact_complete and not result.video_complete
    assert result.files[keys['removed.jpeg']].error
    assert result.files[keys['removed.jpeg']].missing
    assert result.files[keys['damaged.mp4']].video_error
    assert result.classification(keys['new.mp4']) == 'No matches detected'
    rows = {Path(row[0]).name: row for row in report_rows(result)}
    assert rows['new.mp4'][2] == 'Sin coincidencias detectadas'
    assert not rows['new.mp4'][10] and rows['new.mp4'][11]
    window = MainWindow()
    qtbot.addWidget(window)
    window.scan_done(result)
    window.scope_filter.setCurrentIndex(window.scope_filter.findData(2))
    window.view_filter.setCurrentIndex(window.view_filter.findData(4))
    assert window.visible_keys() == [keys['new.mp4']]
    window.view_filter.setCurrentIndex(window.view_filter.findData(7))
    assert window.visible_keys() == [keys['damaged.mp4']]
    qtbot.waitUntil(lambda: not window.jobs, timeout=5000)


def test_unreadable_same_size_primary_reference_prevents_absence(roots, tmp_path, media):
    result, keys = completed_with_unrelated_failures(roots, tmp_path, media)
    # An unreadable non-video extension may still conceal identical bytes.
    result.files[keys['removed.jpeg']].size = result.files[keys['new.mp4']].size
    assert result.classification(keys['new.mp4']) == 'Error or pending'


def test_secondary_failures_do_not_block_each_other_but_primary_video_failures_do(roots, tmp_path, media):
    result, keys = completed_with_unrelated_failures(roots, tmp_path, media)
    result.files[keys['damaged.mp4']].size = result.files[keys['new.mp4']].size
    assert result.classification(keys['new.mp4']) == 'No matches detected'
    result.files[keys['reference.mp4']].video_error = 'generated read failure'
    assert result.classification(keys['new.mp4']) == 'Error or pending'


def test_unfinished_or_cancelled_comparisons_remain_pending(roots, tmp_path, media):
    result, keys = completed_with_unrelated_failures(roots, tmp_path, media)
    result.comparison_finished = False
    assert result.classification(keys['new.mp4']) == 'Error or pending'
    result.comparison_finished = True
    result.cancelled = True
    assert result.classification(keys['new.mp4']) == 'Error or pending'


def test_rescan_after_removed_image_keeps_other_secondary_error_separate(roots, tmp_path, media):
    result, keys = completed_with_unrelated_failures(roots, tmp_path, media)
    refreshed = scan(result.options, cache_path=tmp_path / 'cache.db')
    assert refreshed.exact_complete and not refreshed.video_complete
    assert refreshed.classification(keys['new.mp4']) == 'No matches detected'
    assert refreshed.display_status(keys['damaged.mp4']) == 'Video read error'


def test_replaced_nonvideo_file_may_now_conceal_an_exact_video_copy(roots, tmp_path, media):
    primary, secondary = roots
    shutil.copy2(media['original'], primary / 'reference.mp4')
    new = secondary / 'new.mp4'
    shutil.copy2(media['different'], new)
    replaced = primary / 'changed.jpeg'
    replaced.write_bytes(b'original small fixture')
    def progress(phase, *_):
        if phase == tr('Analyzing video content') and replaced.stat().st_size < 100:
            replaced.write_bytes(new.read_bytes())
    result = scan(ScanOptions(primary, secondary, similar=True), progress=progress, cache_path=tmp_path / 'cache.db')
    keys = {Path(f.path).name: key for key, f in result.files.items()}
    assert result.files[keys['changed.jpeg']].error
    assert not result.files[keys['changed.jpeg']].missing
    assert result.classification(keys['new.mp4']) == 'Error or pending'
