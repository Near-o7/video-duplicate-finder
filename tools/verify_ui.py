"""Render real Qt widgets and generated video fixtures at a requested scale."""
from pathlib import Path
import argparse
import os
import shutil
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scale", default="1")
    parser.add_argument("--state", choices=["empty", "one", "two"], default="two")
    parser.add_argument("--size", default="1440x960")
    parser.add_argument("--selected", action="store_true")
    parser.add_argument("--language", choices=["en","es"], default="es")
    parser.add_argument("--theme", choices=["light","dark","system"], default="light")
    args = parser.parse_args()
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    os.environ["QT_SCALE_FACTOR"] = args.scale
    from PySide6.QtWidgets import QApplication
    from comparador.ui import MainWindow
    from comparador.models import ScanOptions
    from comparador.engine import scan
    from comparador.video import run_media, binary
    workspace = Path(__file__).resolve().parents[1]
    artifacts = workspace / "artifacts"
    artifacts.mkdir(exist_ok=True)
    demo = artifacts / "demo-v12"
    a, b = demo / "Primary collection", demo / "Secondary collection"
    a.mkdir(parents=True, exist_ok=True)
    b.mkdir(parents=True, exist_ok=True)
    original = a / "Sample original.mp4"
    cancel = threading.Event()
    if not original.exists():
        run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                   "testsrc2=size=640x360:rate=12:duration=24", "-c:v", "libx264", str(original)], cancel)
        shutil.copy2(original, b / "Sample copy.mp4")
        run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-ss", "1", "-i", str(original), "-t", "22",
                   "-vf", "scale=320:180", "-c:v", "libx264", "-crf", "26", str(b / "Sample edited.mkv")], cancel)
        (b / "Notes.txt").write_text("Secondary-only file", encoding="utf-8")
        (a / "Inventory.txt").write_text("Primary collection", encoding="utf-8")
    app = QApplication([])
    window = MainWindow()
    from dataclasses import replace
    window.apply_preferences(replace(window.preferences,language=args.language,theme=args.theme))
    window.resize(*map(int, args.size.split("x")))
    if args.state != "empty":
        options = ScanOptions(a if args.state == "two" else b, b if args.state == "two" else None, similar=True)
        result = scan(options, cache_path=artifacts / "demo-cache.db")
        window.primary_path.setText(str(options.primary))
        window.folder_mode.setCurrentIndex(1 if args.state == "two" else 0)
        window.secondary_path.setText(str(b) if args.state == "two" else "")
        window.analysis_mode.setCurrentIndex(1)
        window.new_scan = True
        window.scan_done(result)
        window._set_busy(False)
        for r in range(window.table.rowCount()):
            if "edited" in window.table.item(r, 1).text():
                window.table.selectRow(r)
                break
        if args.selected:
            window.select_redundant()
    window.show()
    limit = time.monotonic() + 15
    while time.monotonic() < limit:
        app.processEvents()
        if not window.jobs:
            break
        time.sleep(0.03)
    for _ in range(10):
        app.processEvents()
        time.sleep(0.02)
    output = artifacts / f"gui-v12-{args.language}-{args.theme}-{args.state}-{args.scale.replace('.', '_')}-{args.size}{'-selected' if args.selected else ''}.png"
    window.grab().save(str(output))
    for job in window.jobs:
        job.cancel.set()
    while window.jobs:
        app.processEvents()
        time.sleep(0.02)
    window.close()
    print(output)


if __name__ == "__main__":
    main()
