from __future__ import annotations
from .i18n import tr
from collections import defaultdict
from pathlib import Path
import hashlib
import os
import threading
from .cache import Cache
from .models import Cancelled, FileRecord, ScanOptions, ScanResult, VIDEO_EXTENSIONS
from .video import cancel_check, probe, fingerprint, fast_fingerprint, find_similar

def hash_file(path, cancel=None):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while (chunk := stream.read(4 * 1024 * 1024)):
            cancel_check(cancel)
            digest.update(chunk)
    cancel_check(cancel)
    return digest.hexdigest()

def partial_hash(record, cancel):
    digest = hashlib.sha256()
    with open(record.path, 'rb') as stream:
        for offset in sorted({0, max(0, record.size // 2 - 32768), max(0, record.size - 65536)}):
            cancel_check(cancel)
            stream.seek(offset)
            digest.update(stream.read(65536))
    if not record.unchanged():
        raise OSError(tr('The file changed while it was being read.'))
    return digest.hexdigest()

def _enumerate(root, role, options, result, cancel, progress, physical):
    pending = [root]
    while pending:
        cancel_check(cancel)
        directory = pending.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    cancel_check(cancel)
                    try:
                        if entry.is_symlink() or (hasattr(os.path, 'isjunction') and os.path.isjunction(entry.path)):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            if options.recursive:
                                pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            path = Path(entry.path)
                            if options.videos_only and path.suffix.lower() not in VIDEO_EXTENSIONS:
                                continue
                            s = path.stat(follow_symlinks=False)
                            record = FileRecord(str(path), role, str(path.relative_to(root)), s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino)
                            identity = (s.st_dev, s.st_ino)
                            if identity in physical and s.st_ino:
                                record.error = tr('This links to the same physical file: {p0}. It is not an independent copy.', p0=f'{physical[identity]}')
                            physical[identity] = str(path)
                            result.files[record.key] = record
                            progress(tr('Exploring folders'), len(result.files), 0, str(path))
                    except OSError as exc:
                        result.errors.append(f'{entry.path}: {exc}')
        except OSError as exc:
            result.errors.append(f'{directory}: {exc}')

def scan(options: ScanOptions, cancel=None, progress=None, cache_path=None):
    options.validate()
    cancel = cancel or threading.Event()
    progress = progress or (lambda *args: None)
    result = ScanResult(options)
    cache = Cache(cache_path)
    try:
        physical = {}
        _enumerate(options.primary, 'primary', options, result, cancel, progress, physical)
        if options.secondary:
            _enumerate(options.secondary, 'secondary', options, result, cancel, progress, physical)
        cancel_check(cancel)
        sizes = defaultdict(list)
        for record in result.files.values():
            if not record.error:
                sizes[record.size].append(record)
        samples = defaultdict(list)
        candidates = [f for group in sizes.values() if len(group) > 1 for f in group]
        for i, record in enumerate(candidates):
            cancel_check(cancel)
            progress(tr('Filtering different files'), i + 1, len(candidates), record.path)
            try:
                samples[record.size, partial_hash(record, cancel)].append(record)
            except OSError as exc:
                record.error = str(exc)
        full = [f for group in samples.values() if len(group) > 1 for f in group]
        hashes = defaultdict(list)
        for i, record in enumerate(full):
            cancel_check(cancel)
            progress(tr('Confirming exact copies with SHA-256'), i + 1, len(full), record.path)
            try:
                record.digest = cache.get(record).get('digest') or hash_file(record.path, cancel)
                if not record.unchanged():
                    raise OSError(tr('The file changed during the scan.'))
                hashes[record.digest].append(record.key)
                cache.put(record, digest=record.digest)
            except OSError as exc:
                record.error = str(exc)
        result.exact_groups = [group for group in hashes.values() if len(group) > 1]
        result.exact_complete = not result.errors and (not any((f.error for f in result.files.values())))
        videos = [f for f in result.files.values() if f.is_video and (not f.error)]
        content_cache = {}
        for i, record in enumerate(videos):
            cancel_check(cancel)
            progress(tr('Analyzing video content') if options.similar else tr('Reading video metadata'), i + 1, len(videos), record.path)
            try:
                payload = cache.get(record)
                shared = content_cache.get(record.digest, {}) if record.digest else {}
                record.metadata = payload.get('metadata') or shared.get('metadata') or probe(record.path, cancel)
                if 'video_stream_index' not in record.metadata:
                    record.metadata = probe(record.path, cancel)
                if options.similar:
                    cache_key = 'fingerprint_fast_v3' if options.video_profile == 'fast' else 'fingerprint_full_v3'
                    record.fingerprint = payload.get(cache_key) or shared.get(cache_key)
                    if not record.fingerprint:
                        if options.video_profile == 'fast':

                            def sample_progress(current, total):
                                progress(tr('Video sample {p0}/{p1}, file {p2}/{p3}', p0=f'{current}', p1=f'{total}', p2=f'{i + 1}', p3=f'{len(videos)}'), i + 1, len(videos), record.path)
                            record.fingerprint = fast_fingerprint(record.path, record.metadata, cancel, sample_progress)
                        else:
                            record.fingerprint = fingerprint(record.path, record.metadata, cancel)
                if not record.unchanged():
                    raise OSError(tr('The video changed during the scan.'))
                updates = {'metadata': record.metadata}
                if options.similar:
                    updates[cache_key] = record.fingerprint
                cache.put(record, **updates)
                if record.digest:
                    content_cache[record.digest] = updates
            except (OSError, RuntimeError, ValueError, EOFError) as exc:
                record.video_error = str(exc)
        if options.similar:
            result.similar_matches = find_similar(list(result.files.values()), options.similarity, options.coverage, cancel, progress)
        result.video_complete = not any((f.video_error for f in videos))
        for record in result.files.values():
            if not record.error and (not record.unchanged()):
                record.error = tr('The file changed or disappeared during the scan. Scan again.')
                result.exact_complete = False
            if record.error:
                try:
                    Path(record.path).stat()
                except FileNotFoundError:
                    record.missing = True
                except OSError:
                    pass
        result.exact_groups = [[k for k in g if not result.files[k].error] for g in result.exact_groups]
        result.exact_groups = [g for g in result.exact_groups if len(g) > 1]
        result.similar_matches = [m for m in result.similar_matches if not result.files[m.a].error and (not result.files[m.b].error)]
        cancel_check(cancel)
        result.comparison_finished = True
    except Cancelled:
        result.cancelled = True
        result.exact_complete = False
        result.video_complete = False
    finally:
        cache.close()
    return result
