"""Render dropdowns and batch reference dialogs after a simulated dark palette."""
from pathlib import Path
import argparse
import os
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
parser = argparse.ArgumentParser()
parser.add_argument("--scale", default="1")
args = parser.parse_args()
os.environ["QT_QPA_PLATFORM"] = "offscreen"
os.environ["QT_SCALE_FACTOR"] = args.scale
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPalette, QColor
from comparador.ui import MainWindow
from comparador.models import ScanOptions
from comparador.engine import scan

app = QApplication([])
dark = QPalette()
dark.setColor(QPalette.ColorRole.Base, QColor("#151515"))
dark.setColor(QPalette.ColorRole.Text, QColor("#eeeeee"))
app.setPalette(dark)
window = MainWindow()
window.show()
window.folder_mode.showPopup()
for _ in range(5):
    app.processEvents()
output = Path(__file__).resolve().parents[1] / "artifacts"
window.folder_mode.view().window().grab().save(str(output / f"selector-{args.scale}.png"))
window.folder_mode.hidePopup()
root = output / "demo-v12"
result = scan(ScanOptions(root / "Primary collection", root / "Secondary collection", similar=True), cache_path=output / "demo-cache.db")
window.scan_done(result)
keys = [k for k, f in result.files.items() if f.root == "secondary" and result.visual_peers(k) and not result.exact_peers(k)]
dialog, combos = window.keeper_dialog(keys)
dialog.show()
for _ in range(5):
    app.processEvents()
dialog.grab().save(str(output / f"dialogo-referencias-{args.scale}.png"))
for job in window.jobs:
    job.cancel.set()
while window.jobs:
    app.processEvents()
    time.sleep(0.01)
dialog.close()
window.close()
print(output)
