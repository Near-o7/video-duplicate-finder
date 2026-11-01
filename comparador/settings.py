"""Preferences contain defaults only. File paths and selections are never saved."""
from dataclasses import dataclass, asdict, fields, field
from pathlib import Path
import json
import os

from .cache import data_dir
from .limits import MIN_SIMILARITY, MAX_SIMILARITY

RESULT_COLUMNS = (
    ('remove', 'Remove'), ('file', 'File'), ('matches', 'Matches with'), ('location', 'Location'),
    ('size', 'Size'), ('duration', 'Duration'), ('resolution', 'Resolution'),
    ('match', 'Match'), ('scores', 'Visual and coverage'),
)
REQUIRED_COLUMNS = {'remove', 'file'}
DEFAULT_COLUMN_WIDTHS = {'remove': 110, 'file': 240, 'matches': 270, 'location': 90,
                         'size': 82, 'duration': 78, 'resolution': 88, 'match': 140, 'scores': 130}


@dataclass
class Preferences:
    language: str = "system"
    theme: str = "system"
    two_folders: bool = False
    recursive: bool = True
    videos_only: bool = False
    similar: bool = False
    video_profile: str = "fast"
    similarity: int = 90
    coverage: int = 80
    gallery_frames: int = 12
    comparison_position: str = 'right'
    visible_columns: list[str] = field(default_factory=lambda: [key for key, _ in RESULT_COLUMNS])
    column_widths: dict[str, int] = field(default_factory=dict)

    def validate(self):
        if self.language not in ("system", "es", "en") or self.theme not in ("system", "light", "dark"):
            raise ValueError("Invalid language or theme")
        if self.video_profile not in ("fast", "full", "segments"):
            raise ValueError("Invalid video profile")
        if self.comparison_position not in ('right', 'below'):
            raise ValueError('Invalid comparison position')
        minimum_coverage = 10 if self.video_profile == 'segments' else 50
        if not MIN_SIMILARITY <= self.similarity <= MAX_SIMILARITY or not minimum_coverage <= self.coverage <= 100 or self.gallery_frames not in (12, 24):
            raise ValueError("Invalid preference value")
        for field in ("two_folders", "recursive", "videos_only", "similar"):
            if type(getattr(self, field)) is not bool:
                raise ValueError("Invalid boolean preference")
        if not isinstance(self.visible_columns, list) or any(type(key) is not str for key in self.visible_columns):
            raise ValueError('Invalid result columns')
        columns = set(self.visible_columns)
        if len(columns) != len(self.visible_columns) or not REQUIRED_COLUMNS <= columns or not columns <= {key for key, _ in RESULT_COLUMNS}:
            raise ValueError('Invalid result columns')
        if not isinstance(self.column_widths, dict) or any(
            key not in DEFAULT_COLUMN_WIDTHS or type(width) is not int or not 48 <= width <= 2400
            for key, width in self.column_widths.items()
        ):
            raise ValueError('Invalid column widths')


def load_preferences(path=None):
    try:
        payload = json.loads(Path(path or data_dir() / "settings.json").read_text(encoding="utf-8"))
        allowed = {f.name for f in fields(Preferences)}
        result = Preferences(**{k: v for k, v in payload.items() if k in allowed})
        result.validate()
        return result
    except (OSError, ValueError, TypeError, AttributeError):
        return Preferences()


def save_preferences(preferences, path=None):
    preferences.validate()
    target = Path(path or data_dir() / "settings.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(".tmp")
    try:
        temp.write_text(json.dumps(asdict(preferences), indent=2), encoding="utf-8")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)
