from __future__ import annotations

import stat
import sys
import textwrap
import threading
import time
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from shazam_desktop.audio.backends import macos_system
from shazam_desktop.audio.backends.macos_backend import MacOSBackend
from shazam_desktop.audio.backends.macos_system import HelperStream, open_helper_stream
from shazam_desktop.audio.sources import SYSTEM_KEY, AudioSource, SourceCatalog, SourceKind
from shazam_desktop.errors import ErrorKind, RecognitionError
from tests.fakes import MIC, SYSTEM, FakeStream

PRELUDE = """
import json, os, sys, time
def event(name, **fields):
    sys.stderr.write(json.dumps({"event": name, **fields}) + "\\n"); sys.stderr.flush()
def pcm(*samples):
    sys.stdout.buffer.write(b"".join(int(s).to_bytes(2, "little", signed=True) for s in samples))
    sys.stdout.buffer.flush()
def serve():
    sys.stdin.buffer.read()
"""


def helper(body: str) -> list[str]:
    return [sys.executable, "-c", PRELUDE + textwrap.dedent(body)]


def open_fake(
    body: str,
    on_frames: Any = None,
    *,
    ready_timeout: float = macos_system.READY_TIMEOUT,
    prompt_timeout: float = macos_system.PROMPT_TIMEOUT,
) -> HelperStream:
    return open_helper_stream(
        Path("unused"),
        on_frames or (lambda _: None),
        command=helper(body),
        ready_timeout=ready_timeout,
        prompt_timeout=prompt_timeout,
    )


def wait_for(condition: Any, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        assert time.monotonic() < deadline, "condition not reached"
        time.sleep(0.01)


# --- helper process -------------------------------------------------------------------------


def test_stream_delivers_pcm_after_ready() -> None:
    frames: list[np.ndarray] = []
    stream = open_fake(
        """
        event("ready", backend="tap", rate=16000)
        pcm(1, -2, 3)
        serve()
        """,
        frames.append,
    )
    wait_for(lambda: frames)
    assert stream.sample_rate == 16000
    assert frames[0].dtype == np.int16
    assert frames[0].tolist() == [1, -2, 3]
    assert stream.failure is None
    stream.close()
    assert stream.failure is None


def test_pcm_split_inside_a_sample_is_reassembled() -> None:
    frames: list[int] = []
    stream = open_fake(
        """
        event("ready")
        sys.stdout.buffer.write(bytes([0x34])); sys.stdout.buffer.flush()
        time.sleep(0.1)
        sys.stdout.buffer.write(bytes([0x12, 0x01])); sys.stdout.buffer.flush()
        time.sleep(0.1)
        sys.stdout.buffer.write(bytes([0x00])); sys.stdout.buffer.flush()
        serve()
        """,
        lambda samples: frames.extend(samples.tolist()),
    )
    wait_for(lambda: len(frames) >= 2)
    stream.close()
    assert frames == [0x1234, 0x0001]


def test_closing_asks_the_helper_to_stop() -> None:
    stream = open_fake('event("ready"); serve()')
    process = stream._process
    stream.close()
    assert process.poll() == 0


def test_permission_denied_before_capture_starts() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake(
            """
            event("error", code="permission_denied", message="not allowed")
            sys.exit(2)
            """
        )
    assert raised.value.kind is ErrorKind.SYSTEM_AUDIO_DENIED
    assert raised.value.detail == "not allowed"


def test_exit_status_alone_identifies_a_denial() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake("sys.exit(2)")
    assert raised.value.kind is ErrorKind.SYSTEM_AUDIO_DENIED


def test_unsupported_os_is_a_source_problem() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake('event("error", code="unsupported_os", message="too old"); sys.exit(3)')
    assert raised.value.kind is ErrorKind.SOURCE_UNAVAILABLE


def test_crash_before_ready_is_a_helper_failure() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake("os._exit(139)")
    assert raised.value.kind is ErrorKind.HELPER_FAILED
    assert "139" in raised.value.detail


def test_reported_capture_failure_is_a_helper_failure() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake('event("error", code="capture_failed", message="boom"); sys.exit(4)')
    assert (raised.value.kind, raised.value.detail) == (ErrorKind.HELPER_FAILED, "boom")


def test_unanswered_permission_prompt_counts_as_a_denial() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake(
            'event("permission_prompt"); time.sleep(30)',
            ready_timeout=0.1,
            prompt_timeout=0.4,
        )
    assert raised.value.kind is ErrorKind.SYSTEM_AUDIO_DENIED


def test_prompt_extends_the_startup_wait() -> None:
    stream = open_fake(
        """
        event("permission_prompt")
        time.sleep(0.5)
        event("ready")
        serve()
        """,
        ready_timeout=0.2,
        prompt_timeout=5,
    )
    stream.close()


def test_silent_helper_times_out_as_a_failure() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_fake("time.sleep(30)", ready_timeout=0.3)
    assert raised.value.kind is ErrorKind.HELPER_FAILED


def test_denial_after_start_surfaces_as_stream_failure() -> None:
    stream = open_fake(
        """
        event("ready")
        pcm(0)
        event("error", code="permission_denied", message="revoked")
        sys.exit(2)
        """
    )
    wait_for(lambda: stream.failure is not None)
    assert stream.failure is not None
    assert stream.failure.kind is ErrorKind.SYSTEM_AUDIO_DENIED
    stream.close()


def test_crash_after_start_surfaces_as_stream_failure() -> None:
    stream = open_fake('event("ready"); os._exit(9)')
    wait_for(lambda: stream.failure is not None)
    assert stream.failure is not None
    assert stream.failure.kind is ErrorKind.HELPER_FAILED
    stream.close()


def test_unparsable_stderr_lines_are_ignored() -> None:
    stream = open_fake('sys.stderr.write("garbage\\n"); event("ready"); serve()')
    assert stream.failure is None
    stream.close()


def test_missing_executable_is_a_helper_failure() -> None:
    with pytest.raises(RecognitionError) as raised:
        open_helper_stream(Path("/nonexistent/shazam-audio-helper"), lambda _: None)
    assert raised.value.kind is ErrorKind.HELPER_FAILED


# --- locating the helper --------------------------------------------------------------------


def make_executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX execute bits")
def test_find_helper_prefers_the_override(tmp_path: Path) -> None:
    helper_path = make_executable(tmp_path / "custom")
    assert macos_system.find_helper({macos_system.HELPER_ENV: str(helper_path)}) == helper_path


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX execute bits")
def test_find_helper_skips_non_executable_files(tmp_path: Path) -> None:
    plain = tmp_path / "custom"
    plain.write_text("x")
    plain.chmod(0o644)
    assert macos_system.find_helper({macos_system.HELPER_ENV: str(plain)}) is None


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX execute bits")
def test_find_helper_uses_the_bundled_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    bundled = make_executable(tmp_path / macos_system.HELPER_NAME)
    monkeypatch.setattr(macos_system, "bundled_helper_dir", lambda: tmp_path)
    assert macos_system.find_helper({}) == bundled


@pytest.mark.parametrize(
    ("version", "supported"),
    [((12, 7, 6), False), ((13, 0), True), ((14, 1), True), ((15,), True), ((), False)],
)
def test_os_support_threshold(version: tuple[int, ...], supported: bool) -> None:
    assert macos_system.os_supports_system_audio(version) is supported


# --- macOS backend --------------------------------------------------------------------------


class _Microphones:
    def __init__(self) -> None:
        self.opened: list[AudioSource] = []

    def list_sources(self) -> SourceCatalog:
        stale_system = AudioSource(
            SYSTEM_KEY, "System Audio", SourceKind.SYSTEM, available=False, hint="old"
        )
        return SourceCatalog((MIC, stale_system))

    def open_stream(self, source: AudioSource, on_frames: Any) -> FakeStream:
        self.opened.append(source)
        return FakeStream(44100)


def backend(
    version: tuple[int, ...] = (14, 5), helper_path: Path | None = Path("/h")
) -> tuple[MacOSBackend, _Microphones]:
    microphones = _Microphones()
    return (
        MacOSBackend(microphones, locate_helper=lambda: helper_path, version=lambda: version),
        microphones,
    )


def test_system_audio_is_offered_with_a_helper_on_a_supported_os() -> None:
    system = backend()[0].list_sources().system
    assert system is not None
    assert (system.available, system.hint) == (True, None)


def test_system_audio_is_disabled_with_a_hint_below_macos_13() -> None:
    system = backend(version=(12, 7))[0].list_sources().system
    assert system is not None
    assert not system.available
    assert system.hint == macos_system.SYSTEM_HINT_OLD_OS


def test_system_audio_is_disabled_when_the_helper_is_missing() -> None:
    system = backend(helper_path=None)[0].list_sources().system
    assert system is not None
    assert not system.available
    assert system.hint == macos_system.SYSTEM_HINT_NO_HELPER


def test_microphones_pass_through_untouched() -> None:
    subject, microphones = backend()
    assert subject.list_sources().find(MIC.key) == MIC
    subject.open_stream(MIC, lambda _: None)
    assert microphones.opened == [MIC]


def test_opening_system_audio_on_an_old_os_is_refused() -> None:
    subject, _ = backend(version=(12, 0))
    with pytest.raises(RecognitionError) as raised:
        subject.open_stream(SYSTEM, lambda _: None)
    assert raised.value.kind is ErrorKind.SOURCE_UNAVAILABLE


def test_opening_system_audio_starts_the_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[Path] = []
    sentinel = object()

    def fake_open(path: Path, on_frames: Any) -> object:
        started.append(path)
        return sentinel

    monkeypatch.setattr(macos_system, "open_helper_stream", fake_open)
    subject, _ = backend(helper_path=Path("/opt/helper"))
    assert subject.open_stream(SYSTEM, lambda _: None) is sentinel
    assert started == [Path("/opt/helper")]


def test_stream_threads_do_not_leak_after_close() -> None:
    before = threading.active_count()
    stream = open_fake('event("ready"); serve()')
    stream.close()
    wait_for(lambda: threading.active_count() <= before)
