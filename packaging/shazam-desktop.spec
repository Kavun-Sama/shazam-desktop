# PyInstaller spec for shazam-desktop.
#
# Environment:
#   FFMPEG_DIR        directory with the ffmpeg and ffprobe executables to bundle (required)
#   AUDIO_HELPER_DIR  macOS only: directory with the built shazam-audio-helper (required)
#
# Windows builds one windowed .exe; macOS builds "Shazam Desktop.app"; other platforms
# build a plain folder (used for local checks only).
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent  # noqa: F821 - SPECPATH is injected by PyInstaller
sys.path.insert(0, str(ROOT))
from shazam_desktop import __version__  # noqa: E402

ICON_DIR = ROOT / "assets" / "icon"
FFMPEG_DIR = Path(os.environ["FFMPEG_DIR"]).resolve()
EXECUTABLE_SUFFIX = ".exe" if sys.platform == "win32" else ""
TOOLS = [FFMPEG_DIR / f"{name}{EXECUTABLE_SUFFIX}" for name in ("ffmpeg", "ffprobe")]
for tool in TOOLS:
    if not tool.is_file():
        raise SystemExit(f"missing bundled tool: {tool}")

BINARIES = [(str(tool), "ffmpeg") for tool in TOOLS]
if sys.platform == "darwin":
    helper = Path(os.environ["AUDIO_HELPER_DIR"]).resolve() / "shazam-audio-helper"
    if not helper.is_file():
        raise SystemExit(f"missing audio helper: {helper}")
    BINARIES.append((str(helper), "helper"))

# Qt modules the app never imports; keeping them out saves tens of megabytes.
EXCLUDES = [
    "tkinter",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtQuick",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.QtMultimedia",
    "PySide6.QtPdf",
    "PySide6.QtSql",
    "PySide6.QtTest",
]

analysis = Analysis(  # noqa: F821
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=BINARIES,
    datas=[(str(ROOT / name), ".") for name in ("LICENSE", "THIRD_PARTY_NOTICES.md")],
    hiddenimports=[],
    excludes=EXCLUDES,
    noarchive=False,
)
archive = PYZ(analysis.pure)  # noqa: F821

if sys.platform == "win32":
    # One self-contained file; windowed, so no console appears.
    exe = EXE(  # noqa: F821
        archive,
        analysis.scripts,
        analysis.binaries,
        analysis.datas,
        [],
        name="shazam-desktop",
        console=False,
        icon=str(ICON_DIR / "icon.ico"),
        upx=False,
        runtime_tmpdir=None,
    )
else:
    exe = EXE(  # noqa: F821
        archive,
        analysis.scripts,
        [],
        exclude_binaries=True,
        name="shazam-desktop",
        console=False,
        upx=False,
    )
    collected = COLLECT(  # noqa: F821
        exe,
        analysis.binaries,
        analysis.datas,
        name="shazam-desktop",
        upx=False,
    )
    if sys.platform == "darwin":
        app = BUNDLE(  # noqa: F821
            collected,
            name="Shazam Desktop.app",
            icon=str(ICON_DIR / "icon.icns"),
            bundle_identifier="io.github.kavun-sama.shazam-desktop",
            info_plist={
                "CFBundleName": "Shazam Desktop",
                "CFBundleDisplayName": "Shazam Desktop",
                "CFBundleShortVersionString": __version__,
                "CFBundleVersion": __version__,
                "LSMinimumSystemVersion": "11.0",
                "NSHighResolutionCapable": True,
                "NSAudioCaptureUsageDescription": (
                    "Shazam Desktop listens to the audio your Mac is playing "
                    "to identify the music."
                ),
                "NSMicrophoneUsageDescription": (
                    "Shazam Desktop listens through the microphone or an audio input "
                    "to identify the music that is playing."
                ),
            },
        )
