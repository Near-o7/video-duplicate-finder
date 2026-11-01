from __future__ import annotations
from .i18n import tr
from dataclasses import dataclass, field
from pathlib import Path
import os
import time
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.avi', '.mov', '.m4v', '.webm', '.wmv', '.mpg', '.mpeg', '.mts', '.m2ts', '.ts', '.flv', '.3gp', '.vob', '.ogv'}

class Cancelled(Exception):
    pass

def path_key(path: Path) -> str:
    return os.path.normcase(str(path.resolve()))

@dataclass
class ScanOptions:
    primary: Path
    secondary: Path | None = None
    recursive: bool = True
    videos_only: bool = False
    similar: bool = False
    similarity: float = 90.0
    coverage: float = 80.0
    video_profile: str = 'fast'

    def validate(self):
        self.primary = self.primary.resolve()
        if not self.primary.is_dir():
            raise ValueError(tr('Choose a valid primary folder.'))
        if self.secondary:
            self.secondary = self.secondary.resolve()
            if not self.secondary.is_dir():
                raise ValueError(tr('Choose a valid secondary folder.'))
            if self.primary == self.secondary or self.primary in self.secondary.parents or self.secondary in self.primary.parents:
                raise ValueError(tr('Choose different folders. Neither folder can be inside the other.'))
        if not 70 <= self.similarity <= 99 or not 50 <= self.coverage <= 100:
            raise ValueError(tr('Thresholds are outside the allowed range.'))
        if self.video_profile not in ('fast', 'full'):
            raise ValueError(tr('Unknown video profile.'))

@dataclass
class FileRecord:
    path: str
    root: str
    relative: str
    size: int
    mtime_ns: int
    device: int
    inode: int
    digest: str = ''
    error: str = ''
    video_error: str = ''
    metadata: dict = field(default_factory=dict)
    fingerprint: dict = field(default_factory=dict)
    active: bool = True

    @property
    def key(self):
        return path_key(Path(self.path))

    @property
    def is_video(self):
        return Path(self.path).suffix.lower() in VIDEO_EXTENSIONS

    def unchanged(self) -> bool:
        try:
            p = Path(self.path)
            if p.is_symlink():
                return False
            s = p.stat()
            return (s.st_size, s.st_mtime_ns, s.st_dev, s.st_ino) == (self.size, self.mtime_ns, self.device, self.inode)
        except OSError:
            return False

@dataclass
class Match:
    a: str
    b: str
    kind: str
    similarity: float = 100.0
    coverage: float = 100.0
    spans: list = field(default_factory=list)
    estimated: bool = False

@dataclass
class ScanResult:
    options: ScanOptions
    files: dict[str, FileRecord] = field(default_factory=dict)
    exact_groups: list[list[str]] = field(default_factory=list)
    similar_matches: list[Match] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    cancelled: bool = False
    exact_complete: bool = False
    video_complete: bool = False
    created: float = field(default_factory=time.time)

    def exact_peers(self, key):
        for group in self.exact_groups:
            if key in group:
                return [self.files[k] for k in group if k != key and self.files[k].active]
        return []

    def visual_peers(self, key):
        return [(self.files[m.b if m.a == key else m.a], m) for m in self.similar_matches if key in (m.a, m.b) and self.files[m.a].active and self.files[m.b].active]

    def classification(self, key):
        f = self.files[key]
        if not f.active:
            return 'Removed'
        if f.error:
            return 'Error or pending'
        exact = self.exact_peers(key)
        visual = self.visual_peers(key)
        if self.options.secondary and f.root == 'secondary':
            exact = [p for p in exact if p.root == 'primary']
            visual = [(p, m) for p, m in visual if p.root == 'primary']
        if exact:
            return 'Exact copy'
        if visual:
            return 'Possible duplicate'
        if not self.exact_complete or (self.options.similar and (not self.video_complete or f.video_error)):
            return 'Error or pending'
        return 'No matches detected'

    def display_status(self, key):
        record = self.files[key]
        if record.active and record.video_error and not record.error:
            return 'Video read error'
        status = self.classification(key)
        if status == 'Error or pending' and not record.error:
            return 'Comparison incomplete'
        return status

def human_size(value):
    size = float(value)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024 or unit == 'TB':
            return f'{size:.1f} {unit}'
        size /= 1024

def duration_text(seconds):
    if seconds is None:
        return 'N/A'
    seconds = int(seconds)
    return f'{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}'
