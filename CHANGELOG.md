# Changelog

## 1.3.0

- Moved comparison previews to an adjustable side panel by default, with the below-table position available in preferences.
- Compacted preview cards, table rows and surrounding controls while retaining galleries, expanded images and full-path tooltips.
- Consolidated scan counts and moved explanatory text behind Scan details. Kept actionable warnings visible and hid idle progress text.
- Returned focus to the table after preview decisions so arrow navigation preserves removal selections and keeper choices.
- Preserved the active row, matching copy, collapsed panels and divider size when changing preferences.

## 1.2.2

- Added a bounded alternative FFmpeg sampler when the quick PyAV reader fails, using the same timestamps without switching to a full scan.
- Selected the actual video track consistently and excluded embedded cover images from samples and previews.
- Accepted valid stream durations when container durations are unavailable and used video duration instead of a longer audio track.
- Distinguished direct video read errors from comparisons left incomplete by other failed files, including in exported reports.
- Refreshed video metadata and fingerprint caches while retaining exact-file hashes.

## 1.2.1

- Added persisted result-column visibility controls in a dedicated settings tab, with file names and removal selection always visible.
- Restricted one-folder result filters to relevant options and hid secondary-folder controls and counts.
- Added matching file names and shared exact-group or visual-pair identifiers to the result list, alongside explicit keep and removal labels.
- Fixed conflicting keeper choices across visual pairs by retaining earlier dependents when their reference is selected for removal.
- Reused valid per-preview keeper choices in the final confirmation and added file-specific messages for unavailable references.
- Added a persistent Show comparison and Hide comparison button.
- Expanded both per-preview decision buttons to share the available horizontal space.

## 1.2.0

- Added a separate preferences window with persisted defaults, light, dark and system appearance, and English and Spanish interfaces.
- Added keeper and removal-selection controls to both comparison cards, including explicit confirmation before unlocking primary files.
- Added horizontally scrollable frame galleries with lazy loading and a larger frame viewer.
- Hid the progress bar when idle and replaced decorative punctuation in interface prose.
- Prepared an English source repository with an explicit publication allowlist and privacy checks.

## 1.1.0

- Added quick video sampling, bulk selection, clearer secondary-folder actions and a more compact interface.

## 1.0.0

- Added exact and visual duplicate matching, one-folder and two-folder modes, reports and protected file operations.
