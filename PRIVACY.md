# Privacy and local data

The desktop application analyzes local files. It does not send videos, fingerprints, file names or reports to a server. It has no telemetry, account login or automatic update check.

## Data on the device

The historical application data directory is `%LOCALAPPDATA%/ComparadorVideos` on Windows. It contains:

- `settings.json` with language, appearance, default scan options and gallery size. It does not store folder paths, file names, selections or the primary-folder unlock state.
- `cache.sqlite3` with file paths, file identity, metadata, hashes and perceptual fingerprints. Videos are not copied into the cache.
- `operaciones.jsonl` with the paths and outcomes of file operations.
- `errores.log` with diagnostics for unexpected errors.

Exported reports contain the paths and matches from the selected comparison. Review them before sharing them. Gallery images are held in memory and are not added to the repository.

Tests can set `VIDEO_DUPLICATE_FINDER_DATA_DIR` to isolate all application data in a temporary directory.

## Public source review

Only files on the explicit source allowlist are staged for publication. Generated media, screenshots, packages, logs, local settings, reports, caches and virtual environments are excluded. The privacy audit checks the source for absolute home-directory paths and common credential patterns. Additional private terms can be checked locally without storing them in source:

```powershell
python tools/audit_public.py --staged --private-term YOUR_LOCAL_PRIVATE_TERM
```

The initial Git history contains only the reviewed source. Commit metadata uses the public GitHub account identity and its GitHub no-reply address rather than a personal contact address.
