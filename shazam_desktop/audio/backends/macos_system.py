"""System audio on macOS through the bundled Swift helper (``shazam-audio-helper``).

The helper captures the system mix with a Core Audio process tap (macOS 14.2+) or
ScreenCaptureKit (macOS 13 to 14.1) and writes 16 kHz mono s16le PCM to stdout. Diagnostics are
JSON lines on stderr: ``permission_prompt``, ``ready`` and ``error`` (with a ``code``). Closing
the helper's stdin asks it to stop.
"""

from __future__ import annotations

import json
import logging
import os
import platform
import subprocess
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import IO, Any

import numpy as np

from shazam_desktop.audio.backend import FrameCallback
from shazam_desktop.errors import ErrorKind, RecognitionError
from shazam_desktop.runtime import bundled_helper_dir

log = logging.getLogger(__name__)

HELPER_NAME = "shazam-audio-helper"
HELPER_ENV = "SHAZAM_AUDIO_HELPER"
SAMPLE_RATE = 16_000
MIN_MACOS = (13, 0)

SYSTEM_HINT_OLD_OS = "System audio needs macOS 13 or newer."
SYSTEM_HINT_NO_HELPER = "The audio helper is missing. Reinstall the app."

READY_TIMEOUT = 10.0
PROMPT_TIMEOUT = 60.0
_READ_SIZE = 16_384
_POLL = 0.02

_EXIT_DENIED = 2
_EXIT_UNSUPPORTED = 3

_CODE_TO_KIND = {
    "permission_denied": ErrorKind.SYSTEM_AUDIO_DENIED,
    "unsupported_os": ErrorKind.SOURCE_UNAVAILABLE,
    "capture_failed": ErrorKind.HELPER_FAILED,
}
_EXIT_TO_KIND = {
    _EXIT_DENIED: ErrorKind.SYSTEM_AUDIO_DENIED,
    _EXIT_UNSUPPORTED: ErrorKind.SOURCE_UNAVAILABLE,
}

Version = tuple[int, ...]


def macos_version() -> Version:
    """The running macOS release as a tuple, or ``()`` when it cannot be determined."""
    release = platform.mac_ver()[0]
    try:
        return tuple(int(part) for part in release.split("."))
    except ValueError:
        return ()


def os_supports_system_audio(version: Version) -> bool:
    return version[:2] >= MIN_MACOS


def _repo_build_dirs() -> list[Path]:
    package = Path(__file__).resolve().parents[3] / "macos" / "AudioHelper" / ".build"
    return [package / "release", package / "debug"]


def find_helper(environ: Mapping[str, str] | None = None) -> Path | None:
    """Locate the helper: explicit override, the app bundle, then a local Swift build."""
    env = os.environ if environ is None else environ
    candidates: list[Path] = []
    if override := env.get(HELPER_ENV):
        candidates.append(Path(override))
    if (bundled := bundled_helper_dir()) is not None:
        candidates.append(bundled / HELPER_NAME)
    candidates.extend(directory / HELPER_NAME for directory in _repo_build_dirs())
    return next((c for c in candidates if c.is_file() and os.access(c, os.X_OK)), None)


class HelperStream:
    """A running helper process feeding PCM into ``on_frames``.

    Implements :class:`~shazam_desktop.audio.backend.AudioStream`.
    """

    sample_rate = SAMPLE_RATE

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        on_frames: FrameCallback,
        *,
        ready_timeout: float = READY_TIMEOUT,
        prompt_timeout: float = PROMPT_TIMEOUT,
    ) -> None:
        self._process = process
        self._on_frames = on_frames
        self._ready_timeout = ready_timeout
        self._prompt_timeout = prompt_timeout
        self._ready = threading.Event()
        self._prompted = threading.Event()
        self._exited = threading.Event()
        self._closing = False
        self._lock = threading.Lock()
        self._reported: tuple[str, str] | None = None
        self._failure: RecognitionError | None = None
        assert process.stdout is not None
        assert process.stderr is not None
        self._pumps = (
            threading.Thread(target=self._pump_pcm, args=(process.stdout,), daemon=True),
            threading.Thread(target=self._pump_events, args=(process.stderr,), daemon=True),
        )
        for pump in self._pumps:
            pump.start()
        threading.Thread(target=self._watch, daemon=True).start()

    @property
    def failure(self) -> RecognitionError | None:
        with self._lock:
            return self._failure

    def wait_until_ready(self) -> None:
        """Block until capture runs; raises the classified error if the helper gives up."""
        started = time.monotonic()
        while not self._ready.is_set():
            if self._exited.is_set():
                self.close()
                raise self._exit_error()
            limit = self._prompt_timeout if self._prompted.is_set() else self._ready_timeout
            if time.monotonic() - started >= limit:
                prompted = self._prompted.is_set()
                self.close()
                if prompted:
                    raise RecognitionError(
                        ErrorKind.SYSTEM_AUDIO_DENIED, "permission prompt was not answered"
                    )
                raise RecognitionError(ErrorKind.HELPER_FAILED, "helper did not start capturing")
            self._exited.wait(_POLL)

    def close(self) -> None:
        self._closing = True
        process = self._process
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
        for pump in self._pumps:
            pump.join(timeout=1)

    # -- reader threads ---------------------------------------------------------------------

    def _pump_pcm(self, stream: IO[bytes]) -> None:
        carry = b""
        while chunk := stream.read(_READ_SIZE):
            data = carry + chunk
            usable = len(data) - len(data) % 2
            carry = data[usable:]
            if usable == 0 or self._closing:
                continue
            samples = np.frombuffer(data[:usable], dtype="<i2").astype(np.int16)
            try:
                self._on_frames(samples)
            except Exception:
                log.exception("Frame callback failed")

    def _pump_events(self, stream: IO[bytes]) -> None:
        for raw in stream:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                log.debug("Helper: %s", line)
                continue
            self._handle(event)

    def _handle(self, event: Any) -> None:
        if not isinstance(event, dict):
            return
        name = event.get("event")
        if name == "permission_prompt":
            self._prompted.set()
        elif name == "ready":
            log.info("Helper capturing with backend %s", event.get("backend"))
            self._ready.set()
        elif name == "error":
            with self._lock:
                self._reported = (str(event.get("code", "")), str(event.get("message", "")))

    def _watch(self) -> None:
        self._process.wait()
        for pump in self._pumps:
            pump.join(timeout=1)
        if not self._closing:
            error = self._exit_error()
            with self._lock:
                self._failure = error
        self._exited.set()

    def _exit_error(self) -> RecognitionError:
        with self._lock:
            reported = self._reported
        if reported is not None:
            code, message = reported
            return RecognitionError(_CODE_TO_KIND.get(code, ErrorKind.HELPER_FAILED), message)
        returncode = self._process.returncode
        kind = _EXIT_TO_KIND.get(returncode, ErrorKind.HELPER_FAILED)
        return RecognitionError(kind, f"helper exited with status {returncode}")


def open_helper_stream(
    helper: Path,
    on_frames: FrameCallback,
    *,
    command: Sequence[str] | None = None,
    popen: Callable[..., subprocess.Popen[bytes]] = subprocess.Popen,
    ready_timeout: float = READY_TIMEOUT,
    prompt_timeout: float = PROMPT_TIMEOUT,
) -> HelperStream:
    """Start the helper and wait until it is capturing."""
    argv = list(command) if command is not None else [str(helper), "capture"]
    try:
        process = popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
    except OSError as exc:
        raise RecognitionError(ErrorKind.HELPER_FAILED, f"cannot start the helper: {exc}") from exc
    stream = HelperStream(
        process, on_frames, ready_timeout=ready_timeout, prompt_timeout=prompt_timeout
    )
    stream.wait_until_ready()
    return stream
