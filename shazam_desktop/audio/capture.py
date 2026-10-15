"""In-memory capture session on top of an :class:`AudioBackend`."""

from __future__ import annotations

import threading
from collections.abc import Callable
from types import TracebackType

import numpy as np

from shazam_desktop.audio.backend import AudioBackend, AudioStream
from shazam_desktop.audio.pcm import Int16Array, pcm_to_wav, rms_level
from shazam_desktop.audio.sources import AudioSource
from shazam_desktop.errors import RecognitionError


class Capture:
    """Accumulates mono PCM from a source and reports the live input level."""

    def __init__(
        self,
        backend: AudioBackend,
        source: AudioSource,
        on_level: Callable[[float], None],
    ) -> None:
        self._backend = backend
        self._source = source
        self._on_level = on_level
        self._lock = threading.Lock()
        self._chunks: list[bytes] = []
        self._frames = 0
        self._peak = 0
        self._sample_rate = 0
        self._stream: AudioStream | None = None
        self._closed = False

    def __enter__(self) -> Capture:
        stream = self._backend.open_stream(self._source, self._on_frames)
        self._sample_rate = stream.sample_rate
        self._stream = stream
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._closed = True
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.close()

    @property
    def failure(self) -> RecognitionError | None:
        """The error that stopped the underlying stream, if it died on its own."""
        stream = self._stream
        return None if stream is None else stream.failure

    @property
    def seconds(self) -> float:
        """Duration of the audio captured so far."""
        with self._lock:
            frames = self._frames
        return frames / self._sample_rate if self._sample_rate else 0.0

    @property
    def peak(self) -> int:
        """Largest absolute sample seen so far; 0 means digital silence."""
        with self._lock:
            return self._peak

    def to_wav(self) -> bytes:
        """Snapshot everything captured so far as WAV bytes."""
        with self._lock:
            pcm = b"".join(self._chunks)
        return pcm_to_wav(pcm, self._sample_rate)

    def _on_frames(self, samples: Int16Array) -> None:
        if self._closed or samples.size == 0:
            return
        peak = int(np.abs(samples.astype(np.int32)).max())
        with self._lock:
            self._chunks.append(samples.tobytes())
            self._frames += samples.size
            self._peak = max(self._peak, peak)
        self._on_level(rms_level(samples))
