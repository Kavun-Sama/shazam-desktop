"""Test doubles for the audio backend and the recognizer."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np

from shazam_desktop.audio.backend import FrameCallback
from shazam_desktop.audio.pcm import Int16Array
from shazam_desktop.audio.sources import (
    DEFAULT_MIC_KEY,
    SYSTEM_KEY,
    AudioSource,
    SourceCatalog,
    SourceKind,
)
from shazam_desktop.recognition.models import Track

MIC = AudioSource(DEFAULT_MIC_KEY, "Microphone", SourceKind.MICROPHONE, device=0)
SYSTEM = AudioSource(SYSTEM_KEY, "System Audio", SourceKind.SYSTEM, device=1)
DISABLED_SYSTEM = AudioSource(
    SYSTEM_KEY, "System Audio", SourceKind.SYSTEM, available=False, hint="no loopback"
)
TRACK = Track(title="Neon Harbor", artist="The Paper Satellites", cover_url=None)


def tone(seconds: float, rate: int = 16000, amplitude: int = 8000) -> Int16Array:
    t = np.arange(int(seconds * rate)) / rate
    return (amplitude * np.sin(2 * np.pi * 440 * t)).astype(np.int16)


class FakeStream:
    def __init__(self, rate: int) -> None:
        self.sample_rate = rate
        self.closed = False

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeBackend:
    """Delivers ``seconds`` of audio the moment a stream opens (or nothing at all)."""

    seconds: float = 10.0
    rate: int = 16000
    silent: bool = False
    catalog: SourceCatalog = field(default_factory=lambda: SourceCatalog((MIC, SYSTEM)))
    streams: list[FakeStream] = field(default_factory=list)
    gate: threading.Event | None = None
    chunk_delay: float = 0.0

    def list_sources(self) -> SourceCatalog:
        return self.catalog

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> FakeStream:
        stream = FakeStream(self.rate)
        self.streams.append(stream)
        if self.gate is None and self.chunk_delay == 0:
            self._deliver(on_frames)
        else:
            threading.Thread(target=self._deliver_when_open, args=(on_frames,), daemon=True).start()
        return stream

    def _deliver_when_open(self, on_frames: FrameCallback) -> None:
        if self.gate is not None:
            self.gate.wait(5)
        self._deliver(on_frames)

    def _deliver(self, on_frames: FrameCallback) -> None:
        if self.seconds <= 0:
            return
        samples = (
            np.zeros(int(self.seconds * self.rate), dtype=np.int16)
            if self.silent
            else tone(self.seconds, self.rate)
        )
        chunk = self.rate // 2
        for start in range(0, samples.size, chunk):
            on_frames(samples[start : start + chunk])
            if self.chunk_delay:
                time.sleep(self.chunk_delay)


@dataclass
class ScriptedRecognizer:
    """Returns queued outcomes in order; a callable outcome may block or raise."""

    outcomes: list[Track | Exception | Callable[[], Track | None] | None]
    calls: list[bytes] = field(default_factory=list)

    def recognize(self, wav: bytes, *, on_matching: Callable[[], None]) -> Track | None:
        self.calls.append(wav)
        on_matching()
        outcome = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        if callable(outcome):
            return outcome()
        return outcome
