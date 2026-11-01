"""Integration check used on the packaged executable; touches only temporary fixtures."""
from pathlib import Path
import json
import os
import shutil
import tempfile
import threading
import time
import traceback


def run_selftest(report_path):
    report = {"ok": False}
    original_data = os.environ.get("VIDEO_DUPLICATE_FINDER_DATA_DIR")
    try:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from .video import binary, run_media, thumbnail
        from .engine import scan
        from .models import ScanOptions
        from .ui import MainWindow
        from .reports import export_csv, export_html
        from send2trash import send2trash
        with tempfile.TemporaryDirectory(prefix="comparador-selftest-") as temp:
            root = Path(temp)
            os.environ['VIDEO_DUPLICATE_FINDER_DATA_DIR'] = str(root / 'appdata')
            from .settings import Preferences, save_preferences
            save_preferences(Preferences(language='en',theme='light'))
            a, b = root / "Principal", root / "Secundaria"
            a.mkdir()
            b.mkdir()
            cancel = threading.Event()
            run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                       "testsrc2=size=320x180:rate=12:duration=8", "-c:v", "libx264", str(a / "original.mp4")], cancel)
            shutil.copy2(a / "original.mp4", b / "nombre diferente.mp4")
            run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-i", str(a / "original.mp4"),
                       "-vf", "scale=160:90", "-c:v", "libx264", "-crf", "28", str(b / "convertido.mkv")], cancel)
            (b / "nuevo.txt").write_text("Solo en secundaria", encoding="utf-8")
            result = scan(ScanOptions(a, b, similar=True), cache_path=root / "cache.db")
            assert result.exact_complete and result.video_complete
            assert len(result.exact_groups) == 1
            assert result.similar_matches
            assert thumbnail(a / "original.mp4", 2, cancel).startswith(b"\xff\xd8")
            trash_fixture = root / "prueba-papelera-comparador.txt"
            trash_fixture.write_text("Archivo temporal generado para verificar la Papelera.", encoding="utf-8")
            send2trash(str(trash_fixture))
            assert not trash_fixture.exists()
            assert (a / "original.mp4").exists()
            export_csv(result, root / "informe.csv")
            export_html(result, root / "informe.html")
            app = QApplication.instance() or QApplication([])
            window = MainWindow()
            window.scan_done(result)
            assert window.table.rowCount() == 4
            assert not window.selected_keys()
            assert window.scan_button.text() == 'Scan'
            converted = next(f for f in result.files.values() if Path(f.path).name == 'convertido.mkv')
            row = window.visible_keys().index(converted.key)
            window.table.setCurrentCell(row, 1)
            window.show_details()
            window.choose_preview(False)
            from .operations import plan_actions
            planned = plan_actions(result, window.selected_keys(), 'trash', keepers=window.choose_keepers(window.selected_keys()))
            assert len(planned) == 1 and planned[0].key == converted.key
            assert planned[0].keeper not in window.checked_keys
            window.toggle_comparison()
            assert window.preview_scroll.isHidden() and window.comparison_toggle.isEnabled()
            window.toggle_comparison()
            assert not window.preview_scroll.isHidden()
            from dataclasses import replace
            from PySide6.QtGui import QPalette
            window.apply_preferences(replace(window.preferences,theme='dark',language='es'))
            assert window.scan_button.text() == 'Analizar'
            assert window.palette().color(QPalette.ColorRole.Window).lightness() < 100
            assert not window.progress.isVisible()
            assert window.preferred_keepers[converted.key] == planned[0].keeper
            single = scan(ScanOptions(b, similar=True), cache_path=root / 'cache.db')
            window.new_scan = True
            window.scan_done(single)
            assert window.scope_filter.isHidden()
            assert window.view_filter.findData(3) == -1
            assert window.view_filter.findData(4) == -1
            for job in window.jobs:
                job.cancel.set()
            limit = time.monotonic() + 10
            while window.jobs and time.monotonic() < limit:
                app.processEvents()
                time.sleep(0.02)
            assert not window.jobs
            window.close()
            report.update(ok=True, ffmpeg=binary("ffmpeg"), ffprobe=binary("ffprobe"),
                          exact_groups=len(result.exact_groups), visual_pairs=len(result.similar_matches), gui_rows=4, recycle_bin=True)
    except Exception:
        report["error"] = traceback.format_exc()
    finally:
        if original_data is None:
            os.environ.pop('VIDEO_DUPLICATE_FINDER_DATA_DIR',None)
        else:
            os.environ['VIDEO_DUPLICATE_FINDER_DATA_DIR'] = original_data
    Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
