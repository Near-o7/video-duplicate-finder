# Validation

Development validation targets Windows 11 x64 and Python 3.13. Windows 10 support has not been verified in a clean virtual machine.

Run the suite with:

```powershell
python -m pytest -q
```

## Covered behavior

- Exact duplicates with different names, partial-hash collisions and different contents of the same size.
- One-folder and two-folder comparisons, internal duplicates, secondary-file classifications and error handling.
- Transcodes, resized videos, trims, different videos, uniform frames and temporal order.
- Separate quick and full caches, bounded quick sampling and reuse of exact-copy analysis.
- Cancellation, files changed during analysis, permission errors and Unicode paths.
- Primary-folder protection, preserving a reference, preferred keeper choices, late conflicts and partial operation failures.
- Cross-device copy verification using simulated device identities.
- Bulk selection, selections outside filters, per-preview keeper choices and explicit unlock confirmation.
- Preference validation and persistence without paths, English and Spanish interfaces, light and dark palettes, expanded frames and lazy gallery loading.
- Progress hidden when the application is idle.
- One-folder filters exclude secondary-folder options, with consistent filters after language changes.
- Visual keeper selection reaches the final removal confirmation, overlapping pairs retain valid references, and invalid selections identify affected paths.
- Matching file names and pair identifiers in the result list, full-width decision buttons and a persistent comparison toggle.
- Saved result-column visibility, required columns, restoring all columns, and applying settings without losing reviewed keepers.

Creating symbolic links may be skipped when the Windows account lacks the required permission. All media fixtures are generated for the tests.

## Visual checks

```powershell
python tools/verify_ui.py --language en --theme light --selected
python tools/verify_ui.py --language en --theme dark --selected
python tools/verify_ui.py --language es --theme light --scale 1.5 --size 1280x720
python tools/verify_controls.py --scale 1.5
```

Generated captures are local artifacts and must not be committed. They may contain local folder paths even when the media itself is synthetic.

## Portable package

`build.py` runs an integration test against the actual executable with PATH restricted to Windows System32. It verifies bundled multimedia tools, exact and visual matching, report export, GUI construction and sending a generated temporary file to Recycle Bin. `tools/verify_portable.py --native` also loads the native Windows graphical backend.

## Performance context

A generated H.264 MP4 lasting 28 minutes and 2 seconds at 1280 by 720 was used to compare extraction strategies. One local run used 14 quick samples in about 0.20 seconds, compared with 1,682 full samples in about 20.77 seconds. This is not a measurement of a real user video or a performance guarantee. The test has a short regular GOP and repeated synthetic content. Other codecs, GOP structures, drives and workloads can differ substantially.

Use `tools/benchmark_video.py` to repeat this synthetic extraction benchmark. Quick mode trades recall for speed. Full mode remains available for a more sensitive comparison.
