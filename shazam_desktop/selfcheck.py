"""``--self-check``: verify that a (frozen) build has everything it needs to run."""

from __future__ import annotations

import importlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import wave
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from shazam_desktop import __version__
from shazam_desktop.audio.backend import AudioStream, FrameCallback
from shazam_desktop.audio.backends.macos_system import find_helper, macos_version
from shazam_desktop.audio.sources import AudioSource, SourceCatalog, unavailable_catalog
from shazam_desktop.errors import ErrorKind, RecognitionError
from shazam_desktop.recognition.models import Track
from shazam_desktop.runtime import bundled_helper_dir, bundled_tools_dir, is_frozen

_COPYLEFT_FLAGS = ("--enable-gpl", "--enable-nonfree", "--enable-version3")
_TOOL_TIMEOUT = 20


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


Check = Callable[[], str]


class _NullBackend:
    """Audio backend without devices: enough to construct the window."""

    def list_sources(self) -> SourceCatalog:
        return unavailable_catalog("self-check")

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> AudioStream:
        raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, "self-check")


class _NullRecognizer:
    def recognize(self, wav: bytes, *, on_matching: Callable[[], None]) -> Track | None:
        return None


def _qt_imports() -> str:
    for module in ("QtCore", "QtGui", "QtWidgets", "QtNetwork"):
        importlib.import_module(f"PySide6.{module}")
    from PySide6 import __version__ as pyside_version

    return f"PySide6 {pyside_version}"


def _shazam_imports() -> str:
    importlib.import_module("ShazamAPI")
    importlib.import_module("pydub")
    importlib.import_module("numpy")
    importlib.import_module("requests")
    return "ShazamAPI, pydub, numpy, requests"


def _platform_imports() -> str:
    modules: tuple[str, ...] = ()  # Linux is not a target platform
    if sys.platform == "win32":
        modules = (
            "pyaudiowpatch",
            "shazam_desktop.ui.hotkey_windows",
            "shazam_desktop.ui.native_windows",
        )
    elif sys.platform == "darwin":
        modules = (
            "sounddevice",  # loads the bundled PortAudio library
            "objc",
            "AppKit",
            "pynput.keyboard",
            "shazam_desktop.ui.native_macos",
        )
    for module in modules:
        importlib.import_module(module)
    return ", ".join(modules) or "none required"


def expected_helper_backend(version: tuple[int, ...]) -> str:
    """The capture mechanism the helper must pick on a given macOS release."""
    if version[:2] >= (14, 2):
        return "tap"
    return "sck" if version[:2] >= (13, 0) else "none"


def verify_probe(output: str, version: tuple[int, ...]) -> str:
    """Validate the helper's ``--probe`` JSON; returns a one-line summary."""
    info = json.loads(output)
    expected = expected_helper_backend(version)
    if info.get("backend") != expected:
        raise RuntimeError(f"helper chose {info.get('backend')!r}, expected {expected!r}")
    if (info.get("format"), info.get("rate"), info.get("channels")) != ("s16le", 16000, 1):
        raise RuntimeError(f"unexpected output format in {output.strip()}")
    return f"{info['backend']} backend on macOS {info.get('os')}"


def _audio_helper() -> str:
    if sys.platform != "darwin":
        return "not applicable"
    helper = find_helper()
    if helper is None:
        raise RuntimeError("the audio helper was not found")
    if is_frozen():
        directory = bundled_helper_dir()
        if directory is None or helper.resolve().parent != directory.resolve():
            raise RuntimeError(f"the helper resolves to {helper}, outside the bundle")
    probe = subprocess.run(
        [str(helper), "--probe"],
        capture_output=True,
        text=True,
        timeout=_TOOL_TIMEOUT,
        check=True,
    )
    return f"{verify_probe(probe.stdout, macos_version())} [{helper}]"


def _find_tool(name: str) -> Path:
    found = shutil.which(name)
    if found is None:
        raise RuntimeError(f"{name} not found on PATH")
    path = Path(found)
    if is_frozen():
        directory = bundled_tools_dir()
        if directory is None:
            raise RuntimeError("the bundle has no ffmpeg directory")
        if path.resolve().parent != directory.resolve():
            raise RuntimeError(f"{name} resolves to {path}, outside the bundle ({directory})")
    return path


def _run(command: Sequence[str | Path]) -> str:
    result = subprocess.run(
        [str(part) for part in command],
        capture_output=True,
        text=True,
        timeout=_TOOL_TIMEOUT,
        check=True,
    )
    return result.stdout + result.stderr


def _ffmpeg_tools() -> str:
    details = []
    for name in ("ffmpeg", "ffprobe"):
        path = _find_tool(name)
        first_line = _run([path, "-hide_banner", "-version"]).splitlines()[0]
        details.append(f"{first_line} [{path}]")
    if is_frozen():
        buildconf = _run([_find_tool("ffmpeg"), "-hide_banner", "-buildconf"])
        flags = [flag for flag in _COPYLEFT_FLAGS if flag in buildconf]
        if flags:
            raise RuntimeError(f"bundled ffmpeg is not LGPL-only: {' '.join(flags)}")
        details.append("LGPL-only configuration")
    return "; ".join(details)


def _decode_audio() -> str:
    """Run the exact decode path of ShazamAPI (pydub -> ffprobe -> ffmpeg) on a generated WAV."""
    from ShazamAPI import Shazam

    rate = 44100
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(b"\x00\x10\xf0\xef" * rate)  # one second of stereo
    audio = Shazam(buffer.getvalue()).normalizateAudioData(buffer.getvalue())
    if (audio.frame_rate, audio.channels, audio.sample_width) != (16000, 1, 2):
        raise RuntimeError(f"unexpected format {audio.frame_rate} Hz/{audio.channels} ch")
    return f"stereo 44.1 kHz -> mono 16 kHz, {audio.duration_seconds:.1f} s"


def _qt_offscreen() -> str:
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtWidgets import QApplication

    from shazam_desktop.controller import Controller
    from shazam_desktop.settings.config import SettingsStore
    from shazam_desktop.state import Phase, State
    from shazam_desktop.ui.window import MainWindow

    if QApplication.instance() is None:
        QApplication(["shazam-desktop"])
    with tempfile.TemporaryDirectory() as directory:
        store = SettingsStore(Path(directory) / "config.json")
        controller = Controller(_NullBackend(), _NullRecognizer(), store)
        window = MainWindow(controller)
        window.apply_state(State(Phase.LISTENING))
        pixmap = window.grab()
        window.close()
    if pixmap.isNull() or pixmap.width() == 0:
        raise RuntimeError("the window rendered nothing")
    size = f"{pixmap.width()}x{pixmap.height()}"
    return f"{QGuiApplication.platformName()} platform, window rendered {size}"


def default_checks() -> list[tuple[str, Check]]:
    return [
        ("qt imports", _qt_imports),
        ("shazam imports", _shazam_imports),
        ("platform imports", _platform_imports),
        ("audio helper", _audio_helper),
        ("ffmpeg tools", _ffmpeg_tools),
        ("audio decode", _decode_audio),
        ("qt offscreen", _qt_offscreen),
    ]


def run_checks(checks: Sequence[tuple[str, Check]]) -> list[CheckResult]:
    results = []
    for name, check in checks:
        try:
            results.append(CheckResult(name, True, check()))
        except Exception as exc:
            results.append(CheckResult(name, False, f"{type(exc).__name__}: {exc}"))
    return results


def run_self_check(
    report: Path | None = None, checks: Sequence[tuple[str, Check]] | None = None
) -> int:
    """Run all checks, print a report (and save it), and return a process exit code."""
    results = run_checks(default_checks() if checks is None else checks)
    lines = [f"shazam-desktop {__version__} self-check ({sys.platform}, frozen={is_frozen()})"]
    lines += [f"{'ok  ' if r.ok else 'FAIL'} {r.name}: {r.detail}" for r in results]
    passed = all(r.ok for r in results)
    lines.append("self-check passed" if passed else "self-check FAILED")
    text = "\n".join(lines) + "\n"
    # A windowed Windows build has no stdout, hence the optional report file.
    if sys.stdout is not None:
        sys.stdout.write(text)
        sys.stdout.flush()
    if report is not None:
        report.write_text(text, encoding="utf-8")
    return 0 if passed else 1
