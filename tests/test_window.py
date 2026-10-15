"""Smoke test: the window follows the state graph and keeps its size contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from shazam_desktop.controller import Controller
from shazam_desktop.errors import ErrorKind
from shazam_desktop.settings.config import SettingsStore
from shazam_desktop.state import Phase, State
from shazam_desktop.ui.accessibility import SystemPreferences
from shazam_desktop.ui.window import BODY_WIDTH, CARD_HEIGHT, PILL_HEIGHT, MainWindow
from tests.fakes import TRACK, FakeBackend, ScriptedRecognizer


@pytest.fixture
def window(qapp: Any, tmp_path: Path) -> MainWindow:
    controller = Controller(
        FakeBackend(), ScriptedRecognizer([]), SettingsStore(tmp_path / "config.json")
    )
    result = MainWindow(controller, preferences=lambda: SystemPreferences(reduce_motion=True))
    result.present()
    return result


def body_size(window: MainWindow) -> tuple[int, int]:
    margin = (window.width() - BODY_WIDTH) // 2
    return BODY_WIDTH, window.height() - 2 * margin


def test_idle_is_a_pill(window: MainWindow) -> None:
    window.apply_state(State(Phase.IDLE))
    assert body_size(window) == (BODY_WIDTH, PILL_HEIGHT)


@pytest.mark.parametrize("phase", [Phase.LISTENING, Phase.FINGERPRINTING, Phase.MATCHING])
def test_busy_phases_keep_the_pill(window: MainWindow, phase: Phase) -> None:
    window.apply_state(State(phase))
    assert body_size(window) == (BODY_WIDTH, PILL_HEIGHT)


def test_result_expands_into_a_card(window: MainWindow) -> None:
    window.apply_state(State(Phase.RESULT, track=TRACK))
    assert body_size(window) == (BODY_WIDTH, CARD_HEIGHT)


@pytest.mark.parametrize("kind", list(ErrorKind))
def test_every_error_expands_into_a_card(window: MainWindow, kind: ErrorKind) -> None:
    window.apply_state(State(Phase.ERROR, error=kind))
    assert body_size(window) == (BODY_WIDTH, CARD_HEIGHT)


def test_card_collapses_when_a_new_run_starts(window: MainWindow) -> None:
    window.apply_state(State(Phase.RESULT, track=TRACK))
    window.apply_state(State(Phase.LISTENING))
    assert body_size(window) == (BODY_WIDTH, PILL_HEIGHT)
