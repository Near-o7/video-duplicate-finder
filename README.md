# Video Duplicate Finder

A local Windows desktop application for finding exact duplicate files and visually similar videos. Compare one folder or review a secondary folder against a primary collection.

## Features

- Confirm exact duplicates with full-file SHA-256 hashes, regardless of file names.
- Find possible video duplicates using a quick sample scan or a more sensitive full scan.
- Review matches side by side and choose which copy to keep directly below each preview.
- Select extra copies in bulk while preserving references, or select every visible file.
- Move selected files without overwriting existing files, or send duplicates to Recycle Bin after confirmation.
- Browse additional frames horizontally and click a frame to open a larger view with keyboard navigation.
- Use English or Spanish, with light, dark and system appearance modes.
- Save scan defaults in the separate Settings window. Folder paths are never saved as preferences.
- Export HTML and UTF-8 CSV reports in the selected application language.

The primary folder is protected by default when comparing two folders. Choosing to remove a primary file requires explicitly unlocking it for the session. Destructive actions always require confirmation.

## Run from source

Requirements: Windows 10 or 11 x64, Python 3.13, FFmpeg and FFprobe.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe main.py
```

Place FFmpeg and FFprobe on PATH, or place their executables and required DLLs in `vendor/ffmpeg/bin`. No files are uploaded for analysis.

## Scan and review

1. Choose one folder, or a primary and secondary folder.
2. Choose exact matching only or include similar videos, then start the scan.
3. Use **Show files from** to switch between primary, secondary and both folders.
4. Click a row to compare its matches. **Keep this copy** keeps that file unchecked and marks the other copy for removal. This does not delete anything.
5. Review the selection and choose a move destination or Recycle Bin. The confirmation lists every affected file and the copy that will be kept.

The first three gallery frames give an overview. Scroll horizontally or choose **More frames** to load additional moments. Click a frame to expand it, then use the arrow keys to navigate.

Open **Settings > Preferences** to configure language, appearance, scan defaults and gallery size. Theme and language changes preserve the active comparison. Primary-folder unlocking is never stored as a default.

## Understanding video matches

Quick mode seeks to at most 24 sample points instead of decoding the entire video. Coverage is estimated from those samples. It can miss trims and edits that full mode finds. Full mode reads the timeline and retains approximately one frame per second. Both modes ignore audio and present visual candidates for manual review.

Similarity is a fingerprint score, not a probability that two files are interchangeable. Strong crops, watermarks, speed changes and extensive edits may not match. Lowering a threshold reuses existing fingerprints without decoding again. Quick and full fingerprints are cached separately.

## Build a portable executable

```powershell
.\.venv\Scripts\python.exe build.py --ffmpeg-dir PATH_TO_FFMPEG_BIN
.\.venv\Scripts\python.exe tools/verify_portable.py --native
```

The build includes the application, Python runtime, Qt, PyAV, FFmpeg and FFprobe in a portable folder under `dist/v1.2/`. Extract the entire ZIP and run `VideoDuplicateFinder.exe` while keeping `_internal` beside it. The package is checked with a restricted PATH before the ZIP is created.

This repository contains source and synthetic tests only. Local executable packages, media samples, screenshots, reports, caches and preferences are excluded from Git. Dependency notices are described in [THIRD_PARTY.md](THIRD_PARTY.md).

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools/audit_public.py
.\.venv\Scripts\python.exe tools/verify_ui.py --language en --theme dark
```

See [TESTING.md](TESTING.md) for validation details and [PRIVACY.md](PRIVACY.md) for local data handling. The source package keeps its historical `comparador` directory name for import compatibility. English UI strings are the source text, with Spanish translations in `comparador/locales/es.json`.
