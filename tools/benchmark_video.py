"""Repeatable 28:02 720p MP4 decode benchmark. Uses generated content only."""
from pathlib import Path
import json
import sys
import threading
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comparador.video import binary, run_media, probe, fingerprint, fast_fingerprint, fast_segment_fingerprint


def main():
    root = Path(__file__).resolve().parents[1] / "artifacts" / "video-benchmark"
    root.mkdir(parents=True, exist_ok=True)
    seed, video = root / "seed.mp4", root / "28min-720p.mp4"
    cancel = threading.Event()
    if not seed.exists():
        run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-f", "lavfi", "-i",
                   "testsrc2=size=1280x720:rate=30:duration=12", "-c:v", "libx264", "-preset", "ultrafast",
                   "-crf", "30", "-g", "60", str(seed)], cancel)
    if not video.exists():
        run_media([binary("ffmpeg"), "-v", "error", "-nostdin", "-y", "-stream_loop", "-1", "-i", str(seed),
                   "-t", "1682", "-c", "copy", "-movflags", "+faststart", str(video)], cancel)
    metadata = probe(video, cancel)
    data = {"duration_seconds": metadata["duration"], "width": metadata["width"], "height": metadata["height"],
            "source": "generated testsrc2 loop, H.264, 30 fps, GOP 60; not the user's video"}
    for name, fn in (("fast", fast_fingerprint), ("segments_fast", fast_segment_fingerprint), ("full", fingerprint)):
        start = time.perf_counter()
        fp = fn(video, metadata, cancel)
        data[name] = {"seconds": round(time.perf_counter() - start, 3), "samples": len(fp["hashes"])}
        print(name, data[name], flush=True)
    data["speedup"] = round(data["full"]["seconds"] / data["fast"]["seconds"], 1)
    data["segment_extraction_speedup"] = round(data["full"]["seconds"] / data["segments_fast"]["seconds"], 1)
    (root.parent / "video-benchmark.json").write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))


if __name__ == "__main__":
    main()
