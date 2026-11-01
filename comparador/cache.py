from pathlib import Path
import json
import os
import sqlite3

ALGORITHM_VERSION = "phash63-temporal-v2-1s"


def data_dir():
    override = os.environ.get("VIDEO_DUPLICATE_FINDER_DATA_DIR")
    root = Path(override) if override else Path(os.environ.get("LOCALAPPDATA", str(Path.home() / ".local" / "share"))) / "ComparadorVideos"
    root.mkdir(parents=True, exist_ok=True)
    return root


class Cache:
    def __init__(self, path=None):
        self.db = sqlite3.connect(path or data_dir() / "cache.sqlite3", timeout=30)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("CREATE TABLE IF NOT EXISTS entries (path TEXT PRIMARY KEY, stamp TEXT, payload TEXT)")

    @staticmethod
    def stamp(record):
        return f"{record.size}:{record.mtime_ns}:{record.device}:{record.inode}:{ALGORITHM_VERSION}"

    def get(self, record):
        row = self.db.execute("SELECT stamp, payload FROM entries WHERE path=?", (record.key,)).fetchone()
        if row and row[0] == self.stamp(record):
            try:
                return json.loads(row[1])
            except (ValueError, TypeError):
                pass
        return {}

    def put(self, record, **updates):
        payload = self.get(record)
        payload.update(updates)
        self.db.execute("INSERT OR REPLACE INTO entries VALUES (?,?,?)", (record.key, self.stamp(record), json.dumps(payload)))
        self.db.commit()

    def close(self):
        self.db.close()
