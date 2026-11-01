# Changelog

## 1.3.6

- Added an optional quick segment profile with direct seeks to at most 160 captures. It bounds pair-comparison work and estimates shared ranges while keeping the full segment profile available.
- Reused dense fingerprints when available, cached quick segment fingerprints separately, and bounded alternative-reader recovery without silently starting a full decode.
- Added English and Spanish controls, persisted defaults, estimated-coverage notes in previews and reports, and manual-only review for partial video matches.

## 1.3.5

- Added an optional edited-video segment profile that aligns ordered shared runs independently across internal cuts and inserted scenes. It reuses full-profile fingerprints and allows 10% to 100% coverage of the longer video without counting samples twice.
- Added English and Spanish profile controls, saved defaults, matched ranges in existing previews and reports, and sampling guards when applying a different profile.
- Labeled segment candidates as shared video sections. Automatic extra-copy proposals remain limited to exact copies in this profile because other video content may differ.

## 1.3.4

- Lowered minimum visual similarity from 70% to 50% in scan options, saved preferences and engine validation, using shared limits.
- Kept the 90% default and existing coverage range. Applying lower thresholds reuses existing video fingerprints.

## 1.3.3

- Scoped secondary no-match classification to primary reference files so failures in unrelated secondary videos no longer mark readable secondary comparisons as incomplete.
- Tracked completion of comparison work separately from aggregate file errors. Excluded irrelevant failed non-video references by recorded size while preserving uncertainty for possible exact matches and failed primary videos.
- Added report notes explaining completed reference comparisons when other files have issues. Kept existing file-action safeguards unchanged.

## 1.3.2

- Added signature-based FLV reading that tolerates inconsistent previous-tag sizes, including files with renamed extensions, across metadata, quick/full analysis and previews.
- Distinguished completed video comparisons against readable files from actual read failures and unfinished analysis. Added report comparison notes and kept unrelated video failures from affecting non-video exact results.
- Defaulted the table to filename sorting and prevented selection-header sorting from moving marked rows. Preview decisions now retain the active review row, scroll position and arrow navigation.

## 1.3.1

- Added column-header guidance for dragging widths and double-clicking to fit contents.
- Saved column widths automatically, retained them across restarts, language changes and column visibility changes, and flushed pending saves when closing.
- Added a Save-confirmed width reset in preferences without changing visible columns or the active review.

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
