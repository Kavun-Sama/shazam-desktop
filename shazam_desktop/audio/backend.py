"""Backend contract: what a platform audio implementation must provide."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from shazam_desktop.audio.pcm import Int16Array
from shazam_desktop.audio.sources import AudioSource, SourceCatalog
from shazam_desktop.errors import ErrorKind

FrameCallback = Callable[[Int16Array], None]

_PERMISSION_MARKERS = ("denied", "permission", "not authorized", "not authorised")


class AudioStream(Protocol):
    """A running input stream."""

    @property
    def sample_rate(self) -> int: ...

    def close(self) -> None: ...


class AudioBackend(Protocol):
    def list_sources(self) -> SourceCatalog:
        """Enumerate the sources currently offered by the platform."""
        ...

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> AudioStream:
        """Start capturing; ``on_frames`` receives mono int16 chunks on a backend thread.

        Raises :class:`~shazam_desktop.errors.RecognitionError` when the source cannot be opened.
        """
        ...


def classify_open_error(message: str) -> ErrorKind:
    """Map a host-API error message to the user-facing failure class."""
    lowered = message.lower()
    if any(marker in lowered for marker in _PERMISSION_MARKERS):
        return ErrorKind.PERMISSION_DENIED
    return ErrorKind.SOURCE_UNAVAILABLE
