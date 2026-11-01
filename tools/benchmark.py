"""Optional local scale check; creates and removes only synthetic temp files."""
from pathlib import Path
import json
import random
import sys
import tempfile
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from comparador.engine import scan
from comparador.models import FileRecord, ScanOptions
from comparador.video import find_similar


def main():
    report = {}
    with tempfile.TemporaryDirectory(prefix="comparador-scale-") as temp:
        root = Path(temp)
        files = root / "archivos"
        files.mkdir()
        for i in range(5000):
            (files / f"archivo-{i:05d}.bin").write_bytes(f"{i % 4950:08d}".encode() * 128)
        start = time.perf_counter()
        result = scan(ScanOptions(files), cache_path=root / "cache.db")
        report["exact_scan_seconds"] = round(time.perf_counter() - start, 3)
        report["files"] = len(result.files)
        report["exact_groups"] = len(result.exact_groups)
        assert result.exact_complete and len(result.files) == 5000 and len(result.exact_groups) == 50
        rng = random.Random(42)
        records = []
        for i in range(5000):
            record = FileRecord(str(root / f"video-{i}.mp4"), "primary", f"video-{i}.mp4", i, 0, 0, i)
            record.metadata = {"duration": 12}
            record.fingerprint = {"step": 1, "hashes": [rng.getrandbits(63) for _ in range(12)]}
            records.append(record)
        start = time.perf_counter()
        matches = find_similar(records, 90, 80, threading.Event())
        report["synthetic_visual_index_seconds"] = round(time.perf_counter() - start, 3)
        report["synthetic_visual_pairs"] = len(matches)
        assert not matches
    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "benchmark.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
