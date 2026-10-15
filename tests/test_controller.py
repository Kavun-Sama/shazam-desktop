from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol

import pytest
from PySide6.QtCore import QEventLoop

from shazam_desktop.audio.sources import SYSTEM_KEY, SourceCatalog
from shazam_desktop.controller import Controller
from shazam_desktop.errors import ErrorKind, RecognitionError
from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.pipeline import PipelineConfig
from shazam_desktop.settings.config import SettingsStore
from shazam_desktop.state import Phase, State
from tests.fakes import DISABLED_SYSTEM, MIC, TRACK, FakeBackend, ScriptedRecognizer

FAST = PipelineConfig(silence_check=0.5, stall=0.3, deadline=2.0, poll=0.005)


def pump(qapp: Any, condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10)
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.002)


@pytest.fixture
def store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(tmp_path / "config.json")


class Builder(Protocol):
    def __call__(
        self, backend: FakeBackend, recognizer: ScriptedRecognizer, *, ffmpeg: bool = True
    ) -> tuple[Controller, list[State]]: ...


@pytest.fixture
def build(qapp: Any, store: SettingsStore) -> Iterator[Builder]:
    """Controller factory; every controller is shut down so no QThread outlives its test."""
    created: list[Controller] = []

    def factory(
        backend: FakeBackend, recognizer: ScriptedRecognizer, *, ffmpeg: bool = True
    ) -> tuple[Controller, list[State]]:
        controller = Controller(
            backend, recognizer, store, pipeline_config=FAST, ffmpeg_check=lambda: ffmpeg
        )
        states: list[State] = []
        controller.state_changed.connect(states.append)
        created.append(controller)
        return controller, states

    yield factory
    for controller in created:
        controller.shutdown()


def test_full_run_walks_the_state_graph(qapp: Any, store: SettingsStore, build: Builder) -> None:
    controller, states = build(FakeBackend(), ScriptedRecognizer([TRACK]))
    controller.start()
    pump(qapp, lambda: controller.state.phase is Phase.RESULT)
    assert [s.phase for s in states] == [
        Phase.LISTENING,
        Phase.FINGERPRINTING,
        Phase.MATCHING,
        Phase.RESULT,
    ]
    assert controller.state.track == TRACK


def test_failure_lands_in_error_with_its_kind(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    recognizer = ScriptedRecognizer([RecognitionError(ErrorKind.NETWORK)])
    controller, _ = build(FakeBackend(), recognizer)
    controller.start()
    pump(qapp, lambda: controller.state.phase is Phase.ERROR)
    assert controller.state.error is ErrorKind.NETWORK


def test_missing_ffmpeg_is_reported_at_startup_and_on_start(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    backend = FakeBackend()
    controller, states = build(backend, ScriptedRecognizer([TRACK]), ffmpeg=False)
    controller.preflight()
    assert controller.state == State(Phase.ERROR, error=ErrorKind.FFMPEG_MISSING)
    controller.start()
    assert backend.streams == []
    assert [s.error for s in states] == [ErrorKind.FFMPEG_MISSING] * 2


def test_unavailable_source_is_an_error_not_a_thread(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    backend = FakeBackend(catalog=SourceCatalog((MIC, DISABLED_SYSTEM)))
    controller, _ = build(backend, ScriptedRecognizer([TRACK]))
    controller.select_source(SYSTEM_KEY)
    controller.start()
    assert controller.state.error is ErrorKind.SOURCE_UNAVAILABLE
    assert backend.streams == []


def test_restart_while_running_does_not_spawn_another_run(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    gate = threading.Event()
    backend = FakeBackend(gate=gate)
    controller, states = build(backend, ScriptedRecognizer([TRACK]))

    controller.start()
    controller.start()
    pump(qapp, lambda: len(backend.streams) == 1)
    controller.toggle()  # a second press cancels rather than restarting
    gate.set()
    qapp.processEvents()

    assert len(backend.streams) == 1
    assert [s.phase for s in states] == [Phase.LISTENING, Phase.IDLE]


def test_cancel_returns_to_idle_and_allows_a_new_run(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    gate = threading.Event()
    backend = FakeBackend(gate=gate)
    controller, states = build(backend, ScriptedRecognizer([TRACK]))

    controller.start()
    pump(qapp, lambda: len(backend.streams) == 1)
    controller.cancel()
    assert controller.state.phase is Phase.IDLE
    pump(qapp, lambda: backend.streams[0].closed)

    backend.gate = None

    def restarted() -> bool:
        controller.start()
        return controller.state.active or controller.state.phase is Phase.RESULT

    pump(qapp, restarted)
    pump(qapp, lambda: controller.state.phase is Phase.RESULT)
    assert Phase.IDLE in [s.phase for s in states]
    assert len(backend.streams) == 2


def test_late_results_after_cancel_are_ignored(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    release = threading.Event()

    def late_track() -> Track:
        release.wait(5)
        return TRACK

    recognizer = ScriptedRecognizer([late_track])
    controller, states = build(FakeBackend(), recognizer)

    controller.start()
    pump(qapp, lambda: controller.state.phase is Phase.MATCHING)
    controller.cancel()
    release.set()
    for _ in range(20):
        qapp.processEvents()
        time.sleep(0.005)

    assert controller.state.phase is Phase.IDLE
    assert Phase.RESULT not in [s.phase for s in states]


def test_selected_source_is_persisted(qapp: Any, store: SettingsStore, build: Builder) -> None:
    controller, _ = build(FakeBackend(), ScriptedRecognizer([TRACK]))
    changes: list[str] = []
    controller.source_changed.connect(changes.append)

    controller.select_source(SYSTEM_KEY)
    controller.select_source(SYSTEM_KEY)

    assert changes == [SYSTEM_KEY]
    assert store.load().source_key == SYSTEM_KEY
    assert controller.source_key() == SYSTEM_KEY
    assert controller.source_label() == "System Audio"


def test_vanished_source_falls_back_to_default_microphone(
    qapp: Any, store: SettingsStore, build: Builder
) -> None:
    controller, _ = build(FakeBackend(), ScriptedRecognizer([TRACK]))
    controller.select_source("mic:Unplugged USB")
    assert controller.source_key() == MIC.key
    assert controller.source_label() == "Microphone"
