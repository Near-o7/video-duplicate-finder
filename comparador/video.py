from __future__ import annotations
from .i18n import tr
from collections import Counter, defaultdict
from pathlib import Path
import bisect
import json
import math
import os
import shutil
import subprocess
import sys
import time
import numpy as np
from .models import Cancelled, Match

def binary(name):
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parents[1]))
    candidates = [base / 'bin' / f'{name}.exe', base / 'vendor' / 'ffmpeg' / 'bin' / f'{name}.exe']
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    found = shutil.which(name)
    if not found:
        raise RuntimeError(tr('{p0} was not found. Use the complete portable package.', p0=f'{name}'))
    return found

def run_media(args, cancel, timeout=1800):
    cancel_check(cancel)
    creation = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=creation)
    start = time.monotonic()
    try:
        while True:
            try:
                out, err = proc.communicate(timeout=0.15)
                break
            except subprocess.TimeoutExpired:
                cancel_check(cancel)
                if time.monotonic() - start > timeout:
                    raise RuntimeError(tr('The file analysis exceeded the time limit of {p0} seconds.', p0=f'{timeout}'))
        if proc.returncode:
            raise RuntimeError(err.decode('utf-8', errors='replace')[-1500:] or tr('Could not read the video.'))
        return out
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()

def cancel_check(cancel):
    if cancel and cancel.is_set():
        raise Cancelled()

def media_input_options(path):
    """Identify FLV by its signature, independently of the filename extension."""
    try:
        with open(path, 'rb') as source:
            is_flv = source.read(3) == b'FLV'
    except OSError:
        return []
    return ['-flv_ignore_prevtag', '1'] if is_flv else []

def probe(path, cancel):
    raw = run_media([binary('ffprobe'), '-v', 'error', *media_input_options(path), '-show_format', '-show_streams', '-of', 'json', str(path)], cancel)
    data = json.loads(raw)
    streams = [s for s in data.get('streams', []) if s.get('codec_type') == 'video' and (not s.get('disposition', {}).get('attached_pic'))]
    if not streams:
        raise ValueError(tr('The file has no readable video stream.'))
    s = streams[0]
    duration = 0
    for value in (s.get('duration'), data.get('format', {}).get('duration')):
        try:
            candidate = float(value)
        except (ValueError, TypeError):
            continue
        if math.isfinite(candidate) and candidate > 0:
            duration = candidate
            break
    if duration <= 0:
        raise ValueError(tr('Could not determine the video duration.'))
    return {'duration': duration, 'video_stream_index': s['index'], 'width': s.get('width', 0), 'height': s.get('height', 0), 'codec': s.get('codec_name', ''), 'audio': any((x.get('codec_type') == 'audio' for x in data.get('streams', [])))}
_dct = np.cos(np.pi * (2 * np.arange(32) + 1)[None, :] * np.arange(8)[:, None] / 64)

def perceptual_hash(frame):
    if float(np.std(frame)) < 5.0:
        return None
    coeff = (_dct @ frame.astype(float) @ _dct.T).flatten()[1:]
    bits = coeff > np.median(coeff)
    value = 0
    for bit in bits:
        value = value << 1 | int(bit)
    return value

def fingerprint(path, metadata, cancel):
    step = 1.0 if metadata['duration'] >= 3 else 0.25
    raw = run_media([binary('ffmpeg'), '-v', 'error', '-nostdin', '-threads', '2', *media_input_options(path), '-i', str(path), '-map', '0:V:0', '-an', '-vf', f'fps=1/{step}:start_time=0,scale=32:32:flags=area,format=gray', '-threads', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1'], cancel)
    hashes = []
    for i in range(len(raw) // 1024):
        cancel_check(cancel)
        frame = np.frombuffer(raw, dtype=np.uint8, count=1024, offset=i * 1024).reshape(32, 32)
        hashes.append(perceptual_hash(frame))
    if not hashes:
        raise ValueError(tr('Could not extract frames.'))
    return {'step': step, 'hashes': hashes}

def fast_fingerprint(path, metadata, cancel, progress=None):
    import av
    try:
        return _fast_pyav(path, metadata, cancel, progress)
    except (av.FFmpegError, OSError, ValueError, EOFError) as primary_error:
        cancel_check(cancel)
        try:
            return _fast_ffmpeg(path, metadata, cancel, progress)
        except (OSError, ValueError, RuntimeError, EOFError) as fallback_error:
            raise ValueError(tr('Quick decoding failed with both readers. First reader: {first}. Alternative reader: {second}', first=str(primary_error), second=str(fallback_error))) from fallback_error


def _sample_grid(metadata):
    duration = metadata['duration']
    step = 0.25 if duration < 3 else float(2 ** max(0, math.ceil(math.log2(duration / 24))))
    phase = 0.37 if duration >= 3 else 0.0
    return step, list(np.arange(phase, max(phase + 0.001, duration - 0.1), step))[:24]


def _fast_ffmpeg(path, metadata, cancel, progress=None):
    """Alternative sparse reader, bounded to 45 seconds per video, never a full scan."""
    step, targets = _sample_grid(metadata)
    hashes = []
    deadline = time.monotonic() + 45
    for i, target in enumerate(targets):
        cancel_check(cancel)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError(tr('The alternative video reader exceeded its time limit.'))
        if progress:
            progress(i + 1, len(targets))
        raw = run_media([binary('ffmpeg'), '-v', 'error', '-nostdin', '-threads', '2', '-ss', str(float(target)), *media_input_options(path), '-i', str(path),
                         '-map', '0:V:0', '-frames:v', '1', '-an', '-vf', 'scale=32:32:flags=area,format=gray',
                         '-threads', '1', '-f', 'rawvideo', '-pix_fmt', 'gray', 'pipe:1'], cancel, timeout=min(12, remaining))
        if len(raw) != 1024:
            raise ValueError(tr('Could not read sample {p0}. Try the full profile.', p0=i + 1))
        hashes.append(perceptual_hash(np.frombuffer(raw, dtype=np.uint8).reshape(32, 32)))
    return {'step': step, 'hashes': hashes, 'profile': 'fast', 'estimated': True, 'reader': 'ffmpeg'}


def _fast_pyav(path, metadata, cancel, progress=None):
    """Seek to at most 24 targets, reusing a single indexed decoder.

    Power-of-two intervals retain a common time grid after modest trims.
    Coverage from these sparse samples is explicitly an estimate.
    """
    import av
    step, targets = _sample_grid(metadata)
    hashes = []
    options = {'flv_ignore_prevtag': '1'} if media_input_options(path) else {}
    with av.open(str(path), timeout=(10, 10), options=options) as container:
        index = metadata.get('video_stream_index')
        stream = container.streams[index] if index is not None else container.streams.video[0]
        stream.codec_context.thread_count = 2
        origin = stream.start_time or 0
        for i, target in enumerate(targets):
            cancel_check(cancel)
            if progress:
                progress(i + 1, len(targets))
            container.seek(origin + int(float(target) / float(stream.time_base)), stream=stream, backward=True, any_frame=False)
            chosen = None
            for frame in container.decode(stream):
                cancel_check(cancel)
                if frame.pts is None:
                    continue
                timestamp = float((frame.pts - origin) * stream.time_base)
                if timestamp + 0.02 >= target:
                    chosen = frame
                    break
            if chosen is None:
                raise ValueError(tr('Could not read sample {p0}. Try the full profile.', p0=f'{i + 1}'))
            gray = chosen.reformat(width=32, height=32, format='gray', interpolation='AREA').to_ndarray()
            hashes.append(perceptual_hash(gray))
    if not hashes:
        raise ValueError(tr('Could not extract video samples.'))
    return {'step': step, 'hashes': hashes, 'profile': 'fast', 'estimated': True}

def _bands(value):
    for band in range(7):
        yield (band, value >> band * 9 & 511)

def compare_pair(a, b, similarity, coverage, cancel):
    duration_a, duration_b = (a.metadata['duration'], b.metadata['duration'])
    longest = max(duration_a, duration_b)
    if min(duration_a, duration_b) / longest * 100 + 0.01 < coverage:
        return None
    fa, fb = (a.fingerprint, b.fingerprint)
    ha, hb = (fa['hashes'], fb['hashes'])
    sa, sb = (fa['step'], fb['step'])
    distance_limit = (1 - similarity / 100) * 63
    index = defaultdict(list)
    for j, h in enumerate(hb):
        if h is not None:
            for band in _bands(h):
                index[band].append(j)
    votes = Counter()
    bucket = max(sa, sb)
    stride = max(1, len(ha) // 180)
    for i in range(0, len(ha), stride):
        cancel_check(cancel)
        h = ha[i]
        if h is None:
            continue
        if distance_limit > 6:
            candidates = range(len(hb))
        else:
            candidates = set((j for band in _bands(h) for j in index.get(band, [])))
        for j in candidates:
            other = hb[j]
            if other is not None and (h ^ other).bit_count() <= distance_limit:
                offset = j * sb - i * sa
                if longest - abs(offset) >= longest * coverage / 100 - bucket:
                    votes[round(offset / bucket)] += 1
    best = None
    for offset_bin, _ in votes.most_common(12):
        cancel_check(cancel)
        offset = offset_bin * bucket
        for delta in (-bucket / 2, 0, bucket / 2):
            shift = offset + delta
            hits = []
            for i, h in enumerate(ha):
                if h is None:
                    continue
                t = i * sa
                j = round((t + shift) / sb)
                if j < 0 or j >= len(hb) or hb[j] is None:
                    continue
                score = (1 - (h ^ hb[j]).bit_count() / 63) * 100
                if score + 1e-08 >= similarity:
                    hits.append((t, j * sb, score))
            if len(hits) < 3:
                continue
            bins_a = {round(t / sa) for t, _, _ in hits}
            bins_b = {round(u / sb) for _, u, _ in hits}
            seconds = min(len(bins_a) * sa, len(bins_b) * sb, duration_a, duration_b)
            covered = min(100.0, seconds / longest * 100)
            if covered + 1e-08 < coverage:
                continue
            spans = []
            start_a, start_b, prev_a, prev_b = (hits[0][0], hits[0][1], hits[0][0], hits[0][1])
            for t, u, _ in hits[1:]:
                if t - prev_a > sa * 1.6 or u - prev_b > sb * 1.6:
                    spans.append([start_a, min(prev_a + sa, duration_a), start_b, min(prev_b + sb, duration_b)])
                    start_a, start_b = (t, u)
                prev_a, prev_b = (t, u)
            spans.append([start_a, min(prev_a + sa, duration_a), start_b, min(prev_b + sb, duration_b)])
            mean_score = sum((x[2] for x in hits)) / len(hits)
            match = Match(a.key, b.key, 'similar', mean_score, covered, spans, bool(fa.get('estimated') or fb.get('estimated')))
            if best is None or (match.coverage, match.similarity) > (best.coverage, best.similarity):
                best = match
    return best

def find_similar(records, similarity, coverage, cancel, progress=None):
    eligible = [f for f in records if f.active and f.fingerprint and (not f.error) and (not f.video_error)]
    eligible.sort(key=lambda f: f.metadata['duration'])
    durations = [f.metadata['duration'] for f in eligible]
    visual_index = defaultdict(dict)
    candidates = set()
    for i, f in enumerate(eligible):
        cancel_check(cancel)
        if similarity >= 90:
            neighbors = set()
            for h in f.fingerprint['hashes']:
                cancel_check(cancel)
                if h is not None:
                    for band in _bands(h):
                        for indexed_hash, owners in visual_index.get(band, {}).items():
                            if (h ^ indexed_hash).bit_count() <= (1 - similarity / 100) * 63:
                                neighbors.update(owners)
            for j in neighbors:
                if durations[j] / durations[i] * 100 + 0.01 >= coverage:
                    candidates.add((j, i))
            for h in set(f.fingerprint['hashes']) - {None}:
                for band in _bands(h):
                    visual_index[band].setdefault(h, set()).add(i)
        else:
            lo = bisect.bisect_left(durations, durations[i] * coverage / 100, 0, i)
            candidates.update(((j, i) for j in range(lo, i)))
    matches = []
    for n, (i, j) in enumerate(sorted(candidates)):
        cancel_check(cancel)
        a, b = (eligible[i], eligible[j])
        if progress:
            progress(tr('Comparing videos'), n + 1, len(candidates), a.path)
        if a.digest and a.digest == b.digest:
            continue
        match = compare_pair(a, b, similarity, coverage, cancel)
        if match:
            matches.append(match)
    return matches

def thumbnail(path, at, cancel, width=480, height=270):
    return run_media([binary('ffmpeg'), '-v', 'error', '-nostdin', '-ss', str(max(0, at)), *media_input_options(path), '-i', str(path), '-map', '0:V:0', '-frames:v', '1', '-vf', f'scale={int(width)}:{int(height)}:force_original_aspect_ratio=decrease', '-threads', '1', '-f', 'image2pipe', '-vcodec', 'mjpeg', 'pipe:1'], cancel, timeout=60)
