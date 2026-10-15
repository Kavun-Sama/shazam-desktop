"""Capture → fingerprint → match, with early exit, cancellation and a hard deadline."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from shazam_desktop.audio.backend import AudioBackend
from shazam_desktop.audio.capture import Capture
from shazam_desktop.audio.sources import AudioSource, SourceKind
from shazam_desktop.errors import CancelledError, ErrorKind, RecognitionError
from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.recognizer import Recognizer
from shazam_desktop.state import Phase


@dataclass(frozen=True, slots=True)
class PipelineConfig:
    """Timing of a run, in seconds.

    ``attempt_windows`` are capture lengths at which a recognition attempt is made;
    the first attempt that matches ends the run before the capture window is over.
    """

    attempt_windows: tuple[float, ...] = (5.0, 10.0)
    silence_check: float = 2.0
    stall: float = 3.0
    deadline: float = 20.0
    poll: float = 0.05


@dataclass(frozen=True, slots=True)
class PipelineCallbacks:
    """Progress sinks; both are invoked from pipeline or recognizer threads."""

    on_phase: Callable[[Phase], None]
    on_level: Callable[[float], None]


@dataclass(slots=True)
class _Outcome:
    track: Track | None = None
    error: Exception | None = None


class Pipeline:
    def __init__(
        self,
        backend: AudioBackend,
        recognizer: Recognizer,
        config: PipelineConfig | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._backend = backend
        self._recognizer = recognizer
        self._config = config or PipelineConfig()
        self._clock = clock

    def run(
        self,
        source: AudioSource,
        cancel: threading.Event,
        callbacks: PipelineCallbacks,
    ) -> Track:
        """Identify the track playing on ``source``.

        Raises :class:`CancelledError` when ``cancel`` is set and
        :class:`RecognitionError` for every failure with a user-facing class.
        """
        deadline = self._clock() + self._config.deadline
        windows = self._config.attempt_windows
        with Capture(self._backend, source, callbacks.on_level) as capture:
            for index, window in enumerate(windows):
                self._listen(capture, window, source, cancel, deadline)
                callbacks.on_phase(Phase.FINGERPRINTING)
                track = self._recognize(capture.to_wav(), cancel, deadline, callbacks)
                if track is not None:
                    return track
                if index < len(windows) - 1:
                    callbacks.on_phase(Phase.LISTENING)
        raise RecognitionError(ErrorKind.NO_MATCH)

    def _listen(
        self,
        capture: Capture,
        target: float,
        source: AudioSource,
        cancel: threading.Event,
        deadline: float,
    ) -> None:
        """Block until ``target`` seconds are captured, failing fast on dead sources."""
        config = self._config
        progress_at = self._clock()
        last_seconds = capture.seconds
        while (seconds := capture.seconds) < target:
            if cancel.wait(config.poll):
                raise CancelledError
            now = self._clock()
            if seconds > last_seconds:
                last_seconds, progress_at = seconds, now
            elif now - progress_at >= config.stall:
                raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, "no audio received")
            if now >= deadline:
                raise RecognitionError(ErrorKind.SOURCE_UNAVAILABLE, "capture timed out")
            if seconds >= config.silence_check and capture.peak == 0:
                raise RecognitionError(_silence_error(source), "digital silence")
        if capture.peak == 0:
            raise RecognitionError(_silence_error(source), "digital silence")

    def _recognize(
        self,
        wav: bytes,
        cancel: threading.Event,
        deadline: float,
        callbacks: PipelineCallbacks,
    ) -> Track | None:
        """Run the blocking recognizer off-thread so cancel and deadline stay responsive.

        The client has no request timeout of its own, so an abandoned call is left to
        finish on its daemon thread and its result is dropped.
        """
        results: queue.Queue[_Outcome] = queue.Queue(maxsize=1)
        abandoned = threading.Event()

        def on_matching() -> None:
            if not abandoned.is_set():
                callbacks.on_phase(Phase.MATCHING)

        def work() -> None:
            try:
                results.put(
                    _Outcome(track=self._recognizer.recognize(wav, on_matching=on_matching))
                )
            except Exception as exc:
                results.put(_Outcome(error=exc))

        threading.Thread(target=work, name="recognizer", daemon=True).start()
        try:
            while True:
                try:
                    outcome = results.get(timeout=self._config.poll)
                except queue.Empty:
                    if cancel.is_set():
                        raise CancelledError from None
                    if self._clock() >= deadline:
                        raise RecognitionError(ErrorKind.NETWORK, "timed out") from None
                    continue
                if outcome.error is not None:
                    raise outcome.error
                return outcome.track
        finally:
            abandoned.set()


def _silence_error(source: AudioSource) -> ErrorKind:
    """Digital silence on a microphone means blocked access; elsewhere it means no signal."""
    if source.kind is SourceKind.MICROPHONE:
        return ErrorKind.PERMISSION_DENIED
    return ErrorKind.SOURCE_UNAVAILABLE
