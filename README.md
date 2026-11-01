# Video Duplicate Finder

A local Windows desktop application for finding exact duplicate files and visually similar videos. Compare one folder or review a secondary folder against a primary collection.

## Features

- Confirm exact duplicates with full-file SHA-256 hashes, regardless of file names.
- Find possible video duplicates using a quick sample scan or a more sensitive full scan.
- Review matches side by side and choose which copy to keep directly below each preview.
- See matching file names and shared pair identifiers in the result list, with visible keep and removal choices.
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
3. When comparing two folders, use **Show files from** to switch between primary, secondary and both folders. One-folder scans only show filters relevant to that folder.
4. Click a row to compare its matches. **Keep this copy** keeps that file unchecked and marks the other copy for removal. This does not delete anything.
5. Review the selection and choose a move destination or Recycle Bin. The confirmation lists every affected file and the copy that will be kept.

The first three gallery frames give an overview. Scroll horizontally or choose **More frames** to load additional moments. Click a frame to expand it, then use the arrow keys to navigate.

Use **Hide comparison** and **Show comparison** beside the selection controls to collapse or restore the preview. The **Matches with** column names each file's matching copy. Exact groups use a shared G identifier, and visual pairs use a shared V identifier. Hover over the cell to see all matching paths and use the comparison selector to review additional matches. Visual pairs are direct matches, not groups of interchangeable files.

The comparison appears to the right of the table by default, with both copies stacked vertically. Drag the divider to adjust the space. This keeps the full table height available for browsing. Choose **Settings > Preferences > General > Comparison position** to place the comparison below the table instead. Compact previews retain additional frames, expanded images and full paths in tooltips. Narrow windows use scrolling to keep all columns and comparison controls accessible.

Drag the border between column headers to change a column's width, or double-click the border to fit its contents. Widths are saved automatically and restored on the next launch, including for columns you hide and show later. Choose **Settings > Preferences > Result columns > Reset column widths**, then **Save**, to restore the original widths without changing which columns are visible.

After choosing **Keep this copy** or **Select for removal**, keyboard focus returns to the table. Use the Up and Down arrows to continue reviewing while keeping all removal checkboxes and keeper choices. The header shows the folder and scan counts once. **Scan details** opens the explanatory text, and progress is visible while work is running. Protected-file and hidden-selection warnings remain visible when relevant.

Choosing a copy to keep clears its removal selection. If you later mark that reference for removal, earlier files that depended on it are kept and an explanatory notice appears. A previously reviewed visual keeper goes straight to the final confirmation. If all direct matches are selected for removal, the warning names the file and the matching paths that need a keeper.

Open **Settings > Preferences** to configure language, appearance, scan defaults, gallery size and visible result columns. The **Result columns** tab lets you hide optional columns or restore all of them. File names and removal selection remain visible. Changes apply to existing results after saving and are remembered on the next launch. Theme and language changes preserve the active comparison. Primary-folder unlocking is never stored as a default.

## Understanding video matches

Quick mode seeks to at most 24 sample points instead of decoding the entire video. Coverage is estimated from those samples. It can miss trims and edits that full mode finds. Full mode reads the timeline and retains approximately one frame per second. Both modes ignore audio and present visual candidates for manual review.

If the quick decoder fails, an alternative FFmpeg reader retries the same sample grid, with a 45-second total limit and a 12-second limit per sample. It does not switch to full-video decoding. If both readers fail, the file remains an error. Embedded cover images are excluded from video analysis and previews. Version 1.2.2 refreshes video metadata and fingerprints once to use the corrected stream selection, while retaining exact-file hashes.

**Video read error** identifies a video that could not be read. **No matches (partial comparison)** means that the video was analyzed and compared with readable videos, while other videos were excluded by read failures. **Comparison incomplete** covers work that remains unfinished. None of these states confirms absence from the whole collection. Only failed or unfinished files appear in the issues filter. Non-video files retain their exact-comparison status when video decoding fails elsewhere. Exported reports include a separate **Comparison notes** column for explanations, keeping actual errors in the error column.

When comparing two folders, secondary no-match results depend on the primary reference files. Read errors in other secondary videos do not make a readable secondary file's comparison incomplete. Confirmed missing non-video files of a different recorded size do not prevent completed video comparisons either. Modified or unreadable primary files, missing primary files of the same size, failed primary videos, unknown directory contents and interrupted scans remain uncertain. File-action safeguards still require a stable, completed exact scan, so rerun the scan after files stop changing before moving selections.

FLV inputs are identified by their file signature, including files renamed with another extension. Readers tolerate inconsistent previous-tag size fields using FFmpeg's documented FLV option, without modifying or converting the original files. Existing successful fingerprints remain cached, and failed videos are retried on the next scan.

Similarity is a fingerprint score, not a probability that two files are interchangeable. Strong crops, watermarks, speed changes and extensive edits may not match. Lowering a threshold reuses existing fingerprints without decoding again. Quick and full fingerprints are cached separately.

Minimum visual similarity is adjustable from 50% to 99% in both scan options and preferences. The default remains 90%. Lower values produce more candidates for manual review. Minimum coverage is a separate control and keeps its existing range.

## Build a portable executable

```powershell
.\.venv\Scripts\python.exe build.py --ffmpeg-dir PATH_TO_FFMPEG_BIN
.\.venv\Scripts\python.exe tools/verify_portable.py --native
```

The build includes the application, Python runtime, Qt, PyAV, FFmpeg and FFprobe in a portable folder under `dist/v1.3.4/`. Extract the entire ZIP and run `VideoDuplicateFinder.exe` while keeping `_internal` beside it. The package is checked with a restricted PATH before the ZIP is created.

This repository contains source and synthetic tests only. Local executable packages, media samples, screenshots, reports, caches and preferences are excluded from Git. Dependency notices are described in [THIRD_PARTY.md](THIRD_PARTY.md).

## Development

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe tools/audit_public.py
.\.venv\Scripts\python.exe tools/verify_ui.py --language en --theme dark
```

See [TESTING.md](TESTING.md) for validation details and [PRIVACY.md](PRIVACY.md) for local data handling. The source package keeps its historical `comparador` directory name for import compatibility. English UI strings are the source text, with Spanish translations in `comparador/locales/es.json`.
