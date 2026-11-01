from __future__ import annotations
from .i18n import tr
from dataclasses import dataclass
from pathlib import Path
import json
import os
import shutil
import tempfile
import time
from send2trash import send2trash
from .cache import data_dir
from .engine import hash_file
from .models import ScanResult, path_key
from .video import cancel_check

@dataclass
class PlannedAction:
    key: str
    destination: str = ''
    keeper: str = ''
    collision: bool = False

def plan_actions(result: ScanResult, keys, kind, destination=None, unlocked=False, keepers=None):
    keys = list(dict.fromkeys(keys))
    selected = set(keys)
    keepers = keepers or {}
    if kind not in ('move', 'trash'):
        raise ValueError(tr('Unknown action.'))
    if not selected:
        raise ValueError(tr('Select at least one file.'))
    if result.cancelled or not result.exact_complete:
        raise ValueError(tr('The scan is incomplete or has read errors. Complete a new scan before moving or removing files.'))
    for key in keys:
        record = result.files[key]
        if not record.active or record.error:
            raise ValueError(tr('The result is no longer current: {p0}', p0=f'{record.path}'))
        if result.options.secondary and record.root == 'primary' and (not unlocked):
            raise ValueError(tr('The primary folder is protected. Unlock it to remove files.'))
        if not record.unchanged():
            raise ValueError(tr('The file changed. Scan again: {p0}', p0=f'{record.path}'))
    for group in result.exact_groups:
        active = {k for k in group if result.files[k].active}
        if active & selected and (not active - selected):
            raise ValueError(tr('Keep at least one copy in each exact group unchecked.'))
    reserved = set()
    actions = []
    dest_root = Path(destination).resolve() if destination else None
    if kind == 'move' and (not dest_root or not dest_root.is_dir()):
        raise ValueError(tr('Choose an existing destination folder.'))
    for key in keys:
        record = result.files[key]
        peers = result.exact_peers(key)
        keeper = ''
        if peers:
            available = [p for p in peers if p.key not in selected and p.unchanged()]
            if not available:
                raise ValueError(tr('The reference copy changed or disappeared. Scan again.'))
            available.sort(key=lambda p: (p.root != 'primary', p.path.lower()))
            requested = keepers.get(key)
            keeper = requested if requested in {p.key for p in available} else available[0].key
        elif kind == 'trash':
            keeper = keepers.get(key, '')
            valid = {p.key for p, _ in result.visual_peers(key) if p.key not in selected and p.unchanged()}
            if keeper not in valid:
                raise ValueError(tr('Choose a matching copy to keep before removing a visual candidate.'))
        if keeper and (not result.files[keeper].unchanged() or keeper in selected):
            raise ValueError(tr('The copy to keep is no longer available.'))
        target = ''
        collision = False
        if kind == 'move':
            proposed = dest_root / record.relative
            if not proposed.resolve().is_relative_to(dest_root):
                raise ValueError(tr('The resolved destination is outside the chosen folder.'))
            if path_key(proposed) == key:
                raise ValueError(tr('The file is already at that destination.'))
            original = proposed
            counter = 1
            while proposed.exists() or path_key(proposed) in reserved:
                collision = True
                proposed = original.with_name(f'{original.stem} ({counter}){original.suffix}')
                counter += 1
            reserved.add(path_key(proposed))
            target = str(proposed)
        actions.append(PlannedAction(key, target, keeper, collision))
    return actions

def verified_move(source: Path, destination: Path, expected_digest, cancel=None):
    if destination.exists():
        raise FileExistsError(tr('The destination appeared after confirmation: {p0}', p0=f'{destination}'))
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.stat().st_dev == destination.parent.stat().st_dev:
        cancel_check(cancel)
        if os.name == 'nt':
            source.rename(destination)
        else:
            with destination.open('xb'):
                pass
            try:
                os.replace(source, destination)
            except BaseException:
                destination.unlink(missing_ok=True)
                raise
        return
    descriptor, temp_name = tempfile.mkstemp(prefix='.comparador-', suffix='.partial', dir=destination.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(descriptor, 'wb') as out, source.open('rb') as inp:
            while (chunk := inp.read(4 * 1024 * 1024)):
                cancel_check(cancel)
                out.write(chunk)
            out.flush()
            os.fsync(out.fileno())
        if hash_file(temp, cancel) != expected_digest or hash_file(source, cancel) != expected_digest:
            raise OSError(tr('Copy verification failed. The original file is kept.'))
        shutil.copystat(source, temp)
        cancel_check(cancel)
        if os.name == 'nt':
            temp.rename(destination)
        else:
            with destination.open('xb'):
                pass
            os.replace(temp, destination)
        source.unlink()
    finally:
        temp.unlink(missing_ok=True)

def execute_actions(result, actions, kind, cancel=None, progress=None, trash_func=None, log_path=None):
    progress = progress or (lambda *args: None)
    trash_func = trash_func or send2trash
    outcomes = []
    protected_keepers = {a.keeper for a in actions if a.keeper}
    if protected_keepers & {a.key for a in actions}:
        raise ValueError(tr('A copy to keep is also selected for removal.'))
    for i, action in enumerate(actions):
        cancel_check(cancel)
        record = result.files[action.key]
        progress(tr('Moving files') if kind == 'move' else tr('Sending to Recycle Bin'), i + 1, len(actions), record.path)
        outcome = {'time': time.time(), 'action': kind, 'source': record.path, 'destination': action.destination, 'keeper': '', 'ok': False}
        try:
            if not record.active or not record.unchanged():
                raise ValueError(tr('The file changed or disappeared. Scan again.'))
            source_digest = hash_file(record.path, cancel)
            if record.digest and source_digest != record.digest:
                raise ValueError(tr('The content changed after the scan.'))
            if action.keeper:
                keeper = result.files[action.keeper]
                outcome['keeper'] = keeper.path
                if not keeper.active or not keeper.unchanged():
                    raise ValueError(tr('The reference copy changed or disappeared.'))
                keeper_digest = hash_file(keeper.path, cancel)
                if keeper.digest and keeper_digest != keeper.digest:
                    raise ValueError(tr("The reference copy's content changed."))
                if result.exact_peers(action.key) and source_digest != keeper_digest:
                    raise ValueError(tr('The files are no longer exact copies.'))
                if not record.unchanged() or not keeper.unchanged():
                    raise ValueError(tr('A file changed during verification.'))
            if not record.unchanged():
                raise ValueError(tr('The file changed during verification.'))
            cancel_check(cancel)
            if kind == 'trash':
                if not action.keeper:
                    raise ValueError(tr('There is no copy to keep.'))
                trash_func(record.path)
            else:
                verified_move(Path(record.path), Path(action.destination), source_digest, cancel)
            record.active = False
            outcome['ok'] = True
        except (OSError, RuntimeError, ValueError) as exc:
            outcome['error'] = str(exc)
        outcomes.append(outcome)
        try:
            with open(log_path or data_dir() / 'operaciones.jsonl', 'a', encoding='utf-8') as stream:
                stream.write(json.dumps(outcome, ensure_ascii=False) + '\n')
        except OSError as exc:
            outcome['log_error'] = str(exc)
    return outcomes
