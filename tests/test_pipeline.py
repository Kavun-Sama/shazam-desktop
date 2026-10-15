from __future__ import annotations

import io
import threading
import wave

import pytest

from shazam_desktop.audio.sources import AudioSource
from shazam_desktop.errors import CancelledError, ErrorKind, RecognitionError
from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.pipeline import Pipeline, PipelineCallbacks, PipelineConfig
from shazam_desktop.state import Phase
from tests.fakes import MIC, SYSTEM, TRACK, FakeBackend, ScriptedRecognizer

FAST = PipelineConfig(silence_check=0.5, stall=0.3, deadline=1.0, poll=0.005)


class Recorder:
    def __init__(self) -> None:
        self.phases: list[Phase] = []
        self.levels: list[float] = []
        self.callbacks = PipelineCallbacks(self.phases.append, self.levels.append)


def run(
    backend: FakeBackend,
    recognizer: ScriptedRecognizer,
    *,
    source: AudioSource = MIC,
    config: PipelineConfig = FAST,
    cancel: threading.Event | None = None,
    recorder: Recorder | None = None,
) -> Track:
    recorder = recorder or Recorder()
    pipeline = Pipeline(backend, recognizer, config)
    return pipeline.run(source, cancel or threading.Event(), recorder.callbacks)


def duration(wav: bytes) -> float:
    with wave.open(io.BytesIO(wav)) as reader:
        frames: int = reader.getnframes()
        rate: int = reader.getframerate()
    return frames / rate


def test_match_on_the_first_attempt_ends_the_run_early() -> None:
    backend = FakeBackend(chunk_delay=0.005)
    recognizer = ScriptedRecognizer([TRACK])
    recorder = Recorder()

    assert run(backend, recognizer, recorder=recorder) == TRACK

    assert len(recognizer.calls) == 1
    assert duration(recognizer.calls[0]) == pytest.approx(5.0, abs=0.6)
    assert recorder.phases == [Phase.FINGERPRINTING, Phase.MATCHING]
    assert backend.streams[0].closed


def test_second_attempt_runs_on_the_full_window() -> None:
    backend = FakeBackend(chunk_delay=0.005)
    recognizer = ScriptedRecognizer([None, TRACK])
    recorder = Recorder()

    assert run(backend, recognizer, recorder=recorder) == TRACK

    first, second = (duration(wav) for wav in recognizer.calls)
    assert first == pytest.approx(5.0, abs=0.6)
    assert second == pytest.approx(10.0, abs=0.01)
    assert recorder.phases == [
        Phase.FINGERPRINTING,
        Phase.MATCHING,
        Phase.LISTENING,
        Phase.FINGERPRINTING,
        Phase.MATCHING,
    ]


def test_no_match_after_every_attempt() -> None:
    recognizer = ScriptedRecognizer([None])
    with pytest.raises(RecognitionError) as raised:
        run(FakeBackend(), recognizer)
    assert raised.value.kind is ErrorKind.NO_MATCH
    assert len(recognizer.calls) == 2


def test_levels_come_from_the_captured_signal() -> None:
    recorder = Recorder()
    run(FakeBackend(), ScriptedRecognizer([TRACK]), recorder=recorder)
    assert recorder.levels
    assert all(0.0 < level <= 1.0 for level in recorder.levels)


def test_recognizer_errors_propagate_with_their_kind() -> None:
    recognizer = ScriptedRecognizer([RecognitionError(ErrorKind.FFMPEG_MISSING)])
    with pytest.raises(RecognitionError) as raised:
        run(FakeBackend(), recognizer)
    assert raised.value.kind is ErrorKind.FFMPEG_MISSING


def test_hung_recognizer_hits_the_deadline_as_a_network_error() -> None:
    release = threading.Event()

    def hang() -> None:
        release.wait(5)

    recognizer = ScriptedRecognizer([hang])
    try:
        with pytest.raises(RecognitionError) as raised:
            run(FakeBackend(), recognizer)
    finally:
        release.set()
    assert raised.value.kind is ErrorKind.NETWORK


def test_cancel_interrupts_a_blocked_recognizer() -> None:
    release = threading.Event()
    started = threading.Event()
    cancel = threading.Event()

    def block() -> None:
        started.set()
        release.wait(5)

    recognizer = ScriptedRecognizer([block])
    slow = PipelineConfig(silence_check=0.5, stall=0.3, deadline=30.0, poll=0.005)

    def cancel_once_started() -> None:
        started.wait(2)
        cancel.set()

    threading.Thread(target=cancel_once_started, daemon=True).start()
    try:
        with pytest.raises(CancelledError):
            run(FakeBackend(), recognizer, config=slow, cancel=cancel)
    finally:
        release.set()


def test_cancel_during_capture() -> None:
    gate = threading.Event()
    backend = FakeBackend(gate=gate)
    cancel = threading.Event()
    threading.Timer(0.05, cancel.set).start()
    try:
        with pytest.raises(CancelledError):
            run(backend, ScriptedRecognizer([TRACK]), cancel=cancel)
    finally:
        gate.set()
    assert backend.streams[0].closed


def test_late_matching_signal_from_an_abandoned_call_is_dropped() -> None:
    release = threading.Event()
    recorder = Recorder()

    class LateMatching:
        def recognize(self, wav: bytes, *, on_matching):  # type: ignore[no-untyped-def]
            release.wait(5)
            on_matching()
            return

    pipeline = Pipeline(FakeBackend(), LateMatching(), FAST)
    with pytest.raises(RecognitionError):
        pipeline.run(MIC, threading.Event(), recorder.callbacks)
    release.set()
    threading.Event().wait(0.05)
    assert Phase.MATCHING not in recorder.phases


def test_source_that_never_delivers_audio_is_unavailable() -> None:
    with pytest.raises(RecognitionError) as raised:
        run(FakeBackend(seconds=0), ScriptedRecognizer([TRACK]), source=SYSTEM)
    assert raised.value.kind is ErrorKind.SOURCE_UNAVAILABLE


def test_digital_silence_on_a_microphone_means_blocked_access() -> None:
    recognizer = ScriptedRecognizer([TRACK])
    with pytest.raises(RecognitionError) as raised:
        run(FakeBackend(silent=True), recognizer, source=MIC)
    assert raised.value.kind is ErrorKind.PERMISSION_DENIED
    assert recognizer.calls == []


def test_digital_silence_on_system_audio_means_no_signal() -> None:
    with pytest.raises(RecognitionError) as raised:
        run(FakeBackend(silent=True), ScriptedRecognizer([TRACK]), source=SYSTEM)
    assert raised.value.kind is ErrorKind.SOURCE_UNAVAILABLE


def test_open_failure_surfaces_as_is() -> None:
    class Failing(FakeBackend):
        def open_stream(self, source, on_frames):  # type: ignore[no-untyped-def]
            raise RecognitionError(ErrorKind.PERMISSION_DENIED, "denied")

    with pytest.raises(RecognitionError) as raised:
        run(Failing(), ScriptedRecognizer([TRACK]))
    assert raised.value.kind is ErrorKind.PERMISSION_DENIED
