# Third-party notices

The binaries built from this repository bundle the components below. Their licenses apply to
them, not to the code of shazam-desktop itself.

## FFmpeg (`ffmpeg`, `ffprobe`)

- License: GNU Lesser General Public License, version 2.1 or later
  (<https://www.gnu.org/licenses/old-licenses/lgpl-2.1.html>).
- Version: **8.1.3**, built from the official source tarball
  <https://ffmpeg.org/releases/ffmpeg-8.1.3.tar.xz>
  (SHA-256 `7138d28c96d9d3e3af4ee3d8cad72741f8ffb40da90c1112235dea3ecd3178a3`, verified by the
  build; the release signature was checked against FFmpeg's signing key
  `FCF9 86EA 15E6 E293 A564 4F10 B432 2F04 D676 58D8`).
- Built unmodified by [`packaging/build_ffmpeg.sh`](packaging/build_ffmpeg.sh) with GPL, version-3
  and nonfree code disabled, no external libraries and no autodetected features:

  ```
  --disable-gpl --disable-nonfree --disable-version3 --disable-autodetect --disable-everything
  --disable-doc --disable-debug --disable-network --disable-asm --disable-ffplay
  --disable-avdevice --disable-swscale --enable-static --disable-shared
  --enable-protocol=file,pipe,fd,cache --enable-demuxer=wav --enable-muxer=wav
  --enable-decoder=pcm_s16le,pcm_s16be,pcm_u8,pcm_s24le,pcm_s32le,pcm_f32le,pcm_f64le
  --enable-encoder=pcm_s16le --enable-filter=aresample,aformat,anull,abuffer,abuffersink
  ```

  The bundled programs only read and write PCM WAV, which is all the app needs.
- The programs are separate executables that the app starts as child processes. To use your own
  build, run the app from source (`pip install -e .`) with that build first on `PATH`, or rebuild
  the binaries with `FFMPEG_DIR` pointing at it. The corresponding source is the tarball above plus
  the build script in this repository.

## Qt and PySide6

- Qt 6 (QtCore, QtGui, QtWidgets, QtNetwork) through PySide6 and shiboken6, version 6.12.0.
- License: GNU Lesser General Public License, version 3 (also offered by The Qt Company under
  GPL-2.0 and GPL-3.0 and commercial terms). Text: <https://www.gnu.org/licenses/lgpl-3.0.html>.
- Source: <https://code.qt.io/cgit/pyside/pyside-setup.git/> and <https://www.qt.io/download-open-source>.
- The Qt libraries are shipped as separate shared libraries inside the bundle, not compiled into
  the app's own code. In the macOS app they sit in the `.app` and can be replaced; the Windows
  single-file executable unpacks them on start.

## Other components

| Component | License | Source |
| --- | --- | --- |
| Python | PSF-2.0 | <https://www.python.org/> |
| PyInstaller (bootloader and runtime hooks) | GPL-2.0-or-later with the bootloader exception | <https://pyinstaller.org/> |
| ShazamAPI | MIT (upstream `LICENSE`) | <https://github.com/Numenorean/ShazamAPI> |
| pydub | MIT | <https://github.com/jiaaro/pydub> |
| NumPy | BSD-3-Clause and others | <https://numpy.org/> |
| Requests | Apache-2.0 | <https://requests.readthedocs.io/> |
| sounddevice and PortAudio (macOS) | MIT | <https://python-sounddevice.readthedocs.io/> |
| PyAudioWPatch and PortAudio (Windows) | MIT | <https://github.com/s0d3s/PyAudioWPatch> |
| pynput (macOS) | LGPL-3.0 | <https://github.com/moses-palmer/pynput> |
| PyObjC (macOS) | MIT | <https://github.com/ronaldoussoren/pyobjc> |
| platformdirs | MIT | <https://github.com/tox-dev/platformdirs> |

ShazamAPI's signature code has no copyright header and its structure matches that of the
GPL-3.0 project SongRec. The origin of that code has not been verified here.

Shazam is a trademark of Apple Inc. This project is not affiliated with or endorsed by Apple or
Shazam.
