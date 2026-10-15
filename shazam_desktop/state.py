"""Recognition state machine: Idle → Listening → Fingerprinting → Matching → Result | Error."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum, auto

from shazam_desktop.errors import ErrorKind
from shazam_desktop.recognition.models import Track


class Phase(Enum):
    IDLE = auto()
    LISTENING = auto()
    FINGERPRINTING = auto()
    MATCHING = auto()
    RESULT = auto()
    ERROR = auto()


BUSY_PHASES = frozenset({Phase.LISTENING, Phase.FINGERPRINTING, Phase.MATCHING})


@dataclass(frozen=True, slots=True)
class State:
    phase: Phase = Phase.IDLE
    track: Track | None = None
    error: ErrorKind | None = None

    @property
    def active(self) -> bool:
        return self.phase in BUSY_PHASES


class InvalidTransitionError(RuntimeError):
    """The requested transition is not part of the state graph."""


# Matching → Listening is the retry edge: a failed early attempt resumes capture
# so the next attempt runs on a longer window.
_TRANSITIONS: dict[Phase, frozenset[Phase]] = {
    Phase.IDLE: frozenset({Phase.LISTENING, Phase.ERROR}),
    Phase.LISTENING: frozenset({Phase.FINGERPRINTING, Phase.ERROR, Phase.IDLE}),
    Phase.FINGERPRINTING: frozenset({Phase.MATCHING, Phase.ERROR, Phase.IDLE}),
    Phase.MATCHING: frozenset({Phase.LISTENING, Phase.RESULT, Phase.ERROR, Phase.IDLE}),
    Phase.RESULT: frozenset({Phase.LISTENING, Phase.ERROR}),
    Phase.ERROR: frozenset({Phase.LISTENING, Phase.ERROR}),
}


class StateMachine:
    """Validated transitions between recognition phases."""

    def __init__(self, on_change: Callable[[State], None] | None = None) -> None:
        self._state = State()
        self._on_change = on_change

    @property
    def state(self) -> State:
        return self._state

    def begin(self) -> State:
        """Start a run from Idle, Result or Error."""
        return self._to(State(Phase.LISTENING))

    def advance(self, phase: Phase) -> State:
        """Move between busy phases while a run is in progress."""
        if phase not in BUSY_PHASES or not self._state.active:
            raise InvalidTransitionError(f"{self._state.phase.name} -> {phase.name}")
        return self._to(State(phase))

    def succeed(self, track: Track) -> State:
        return self._to(State(Phase.RESULT, track=track))

    def fail(self, kind: ErrorKind) -> State:
        return self._to(State(Phase.ERROR, error=kind))

    def cancel(self) -> State:
        """Abort an active run and return to Idle."""
        if not self._state.active:
            raise InvalidTransitionError(f"{self._state.phase.name} -> IDLE")
        return self._to(State(Phase.IDLE))

    def _to(self, new: State) -> State:
        if new.phase not in _TRANSITIONS[self._state.phase]:
            raise InvalidTransitionError(f"{self._state.phase.name} -> {new.phase.name}")
        self._state = new
        if self._on_change is not None:
            self._on_change(new)
        return new
