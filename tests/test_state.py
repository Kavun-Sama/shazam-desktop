from __future__ import annotations

import pytest

from shazam_desktop.errors import ErrorKind
from shazam_desktop.recognition.models import Track
from shazam_desktop.state import InvalidTransitionError, Phase, State, StateMachine

TRACK = Track(title="t", artist="a", cover_url=None)


def test_starts_idle() -> None:
    machine = StateMachine()
    assert machine.state == State(Phase.IDLE)
    assert not machine.state.active


def test_happy_path_visits_every_phase_in_order() -> None:
    seen: list[Phase] = []
    machine = StateMachine(on_change=lambda state: seen.append(state.phase))
    machine.begin()
    machine.advance(Phase.FINGERPRINTING)
    machine.advance(Phase.MATCHING)
    machine.succeed(TRACK)
    assert seen == [Phase.LISTENING, Phase.FINGERPRINTING, Phase.MATCHING, Phase.RESULT]
    assert machine.state.track == TRACK


def test_failed_attempt_resumes_listening() -> None:
    machine = StateMachine()
    machine.begin()
    machine.advance(Phase.FINGERPRINTING)
    machine.advance(Phase.MATCHING)
    machine.advance(Phase.LISTENING)
    assert machine.state.phase is Phase.LISTENING


@pytest.mark.parametrize("phase", [Phase.LISTENING, Phase.FINGERPRINTING, Phase.MATCHING])
def test_cancel_from_any_busy_phase_returns_to_idle(phase: Phase) -> None:
    machine = StateMachine()
    machine.begin()
    for step in (Phase.FINGERPRINTING, Phase.MATCHING):
        if machine.state.phase is phase:
            break
        machine.advance(step)
    machine.cancel()
    assert machine.state == State(Phase.IDLE)


def test_error_carries_its_kind() -> None:
    machine = StateMachine()
    machine.begin()
    machine.fail(ErrorKind.NETWORK)
    assert machine.state == State(Phase.ERROR, error=ErrorKind.NETWORK)


def test_preflight_failure_is_allowed_from_idle() -> None:
    machine = StateMachine()
    machine.fail(ErrorKind.FFMPEG_MISSING)
    assert machine.state.phase is Phase.ERROR


@pytest.mark.parametrize("start_from", ["result", "error"])
def test_new_run_can_start_from_a_terminal_state(start_from: str) -> None:
    machine = StateMachine()
    machine.begin()
    if start_from == "result":
        machine.advance(Phase.FINGERPRINTING)
        machine.advance(Phase.MATCHING)
        machine.succeed(TRACK)
    else:
        machine.fail(ErrorKind.NO_MATCH)
    machine.begin()
    assert machine.state == State(Phase.LISTENING)


def test_cannot_skip_fingerprinting() -> None:
    machine = StateMachine()
    machine.begin()
    with pytest.raises(InvalidTransitionError):
        machine.advance(Phase.MATCHING)


def test_cannot_begin_twice() -> None:
    machine = StateMachine()
    machine.begin()
    with pytest.raises(InvalidTransitionError):
        machine.begin()


def test_cannot_succeed_without_matching() -> None:
    machine = StateMachine()
    machine.begin()
    with pytest.raises(InvalidTransitionError):
        machine.succeed(TRACK)


def test_cannot_cancel_when_idle() -> None:
    with pytest.raises(InvalidTransitionError):
        StateMachine().cancel()


@pytest.mark.parametrize("phase", [Phase.IDLE, Phase.RESULT, Phase.ERROR])
def test_advance_rejects_non_busy_targets(phase: Phase) -> None:
    machine = StateMachine()
    machine.begin()
    with pytest.raises(InvalidTransitionError):
        machine.advance(phase)


def test_rejected_transition_keeps_state_and_stays_silent() -> None:
    seen: list[State] = []
    machine = StateMachine(on_change=seen.append)
    with pytest.raises(InvalidTransitionError):
        machine.advance(Phase.LISTENING)
    assert machine.state.phase is Phase.IDLE
    assert seen == []
