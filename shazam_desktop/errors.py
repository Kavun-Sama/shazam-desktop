"""Error taxonomy shared by the pipeline, the controller and the UI."""

from __future__ import annotations

from enum import Enum, auto


class ErrorKind(Enum):
    """User-visible failure classes; each one maps to a card in the UI."""

    NO_MATCH = auto()
    NETWORK = auto()
    FFMPEG_MISSING = auto()
    SOURCE_UNAVAILABLE = auto()
    PERMISSION_DENIED = auto()
    SYSTEM_AUDIO_DENIED = auto()
    HELPER_FAILED = auto()
    UNEXPECTED = auto()


class RecognitionError(Exception):
    """A recognition run failed in a way that has a user-facing class."""

    def __init__(self, kind: ErrorKind, detail: str = "") -> None:
        super().__init__(f"{kind.name}: {detail}" if detail else kind.name)
        self.kind = kind
        self.detail = detail


class CancelledError(Exception):
    """The user cancelled the run."""
