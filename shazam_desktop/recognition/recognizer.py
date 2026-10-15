"""The narrow seam between the app and whichever recognition service backs it."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from shazam_desktop.recognition.models import Track


class Recognizer(Protocol):
    """Identifies a track from in-memory WAV bytes.

    ``on_matching`` is called once, right before the network request starts.
    Implementations raise :class:`~shazam_desktop.errors.RecognitionError` for
    failures that have a user-facing class and return ``None`` for "no match".
    """

    def recognize(self, wav: bytes, *, on_matching: Callable[[], None]) -> Track | None: ...
