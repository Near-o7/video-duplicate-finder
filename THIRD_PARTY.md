# Third-party components

The application uses these components without modifying their source. A local portable build collects the license files provided by the installed distributions into its `licenses` directory and records versions in `versions.json`.

| Component | Project | License information |
|---|---|---|
| Python | https://www.python.org/ | Python Software Foundation license |
| PySide6 Essentials and Shiboken6 | https://www.qt.io/qt-for-python | Qt for Python and Qt component license terms, including LGPL and GPL options |
| NumPy | https://numpy.org/ | BSD license and included dependency notices |
| Send2Trash | https://github.com/arsenetar/send2trash | BSD-3-Clause |
| PyAV | https://pyav.org/ | BSD-3-Clause and bundled multimedia library notices |
| PyInstaller | https://pyinstaller.org/ | GPL with its application distribution exception |
| FFmpeg and FFprobe | https://ffmpeg.org/ | Terms depend on the actual FFmpeg build and enabled libraries |

The build script uses the FFmpeg binaries explicitly selected by the person building the application. It copies their supplied license and records their complete version and configuration output. Rebuilding with another FFmpeg distribution may change its dependencies and applicable terms.

Qt source is available from https://download.qt.io/official_releases/ and PyAV source from https://github.com/PyAV-Org/PyAV . FFmpeg source is available from https://git.ffmpeg.org/ffmpeg.git . Consult the notices and corresponding sources for the exact versions being distributed.

The public repository does not include dependency binaries. Publishing a portable binary package is a separate distribution step and requires satisfying the applicable dependency terms. The application source has no separate license grant selected at this time.
