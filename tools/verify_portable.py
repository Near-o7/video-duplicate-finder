"""Run the actual executable without Python or FFmpeg available in PATH."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from comparador import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--native", action="store_true", help="Also verify the native Windows graphics backend")
    args = parser.parse_args()
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    report = artifacts / ("portable-native-selftest.json" if args.native else "portable-selftest.json")
    report.unlink(missing_ok=True)
    env = os.environ.copy()
    env["PATH"] = str(Path(env.get("WINDIR", "C:/Windows")) / "System32")
    env["QT_QPA_PLATFORM"] = "windows" if args.native else "offscreen"
    for name in ("PYTHONHOME", "PYTHONPATH", "QT_PLUGIN_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        env.pop(name, None)
    executable = ROOT / "dist" / ("v" + __version__) / "VideoDuplicateFinder" / "VideoDuplicateFinder.exe"
    completed = subprocess.run([str(executable), "--self-test", str(report)], env=env, cwd=artifacts, timeout=180, capture_output=True)
    if not report.exists():
        raise RuntimeError(f"The executable did not produce a report. Exit code {completed.returncode}; {completed.stderr!r}")
    data = json.loads(report.read_text(encoding="utf-8"))
    print(json.dumps(data, ensure_ascii=True, indent=2))
    assert completed.returncode == 0 and data["ok"], "Portable verification failed"
    assert "_internal" in data["ffmpeg"] and "_internal" in data["ffprobe"]


if __name__ == "__main__":
    main()
