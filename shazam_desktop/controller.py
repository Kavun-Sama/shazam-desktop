"""Application controller: owns the state machine, the worker thread and the settings."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import replace

from PySide6.QtCore import QObject, Signal, Slot

from shazam_desktop.audio.backend import AudioBackend
from shazam_desktop.audio.sources import DEFAULT_MIC_KEY, SourceCatalog
from shazam_desktop.errors import ErrorKind
from shazam_desktop.recognition.models import Track
from shazam_desktop.recognition.pipeline import Pipeline, PipelineConfig
from shazam_desktop.recognition.preflight import ffmpeg_available
from shazam_desktop.recognition.recognizer import Recognizer
from shazam_desktop.recognition.worker import RecognitionThread
from shazam_desktop.settings.config import Settings, SettingsStore
from shazam_desktop.state import Phase, State, StateMachine

log = logging.getLogger(__name__)


class Controller(QObject):
    """Single entry point for UI actions; at most one recognition thread exists at a time."""

    state_changed = Signal(object)
    level_changed = Signal(float)
    source_changed = Signal(str)

    def __init__(
        self,
        backend: AudioBackend,
        recognizer: Recognizer,
        store: SettingsStore,
        *,
        pipeline_config: PipelineConfig | None = None,
        ffmpeg_check: Callable[[], bool] = ffmpeg_available,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._backend = backend
        self._store = store
        self._settings: Settings = store.load()
        self._ffmpeg_check = ffmpeg_check
        self._pipeline = Pipeline(backend, recognizer, pipeline_config)
        self._machine = StateMachine(on_change=self.state_changed.emit)
        self._thread: RecognitionThread | None = None

    @property
    def state(self) -> State:
        return self._machine.state

    @property
    def settings(self) -> Settings:
        return self._settings

    def sources(self) -> SourceCatalog:
        return self._backend.list_sources()

    def source_key(self) -> str:
        """Key of the selected source, falling back to the default microphone."""
        source = self.sources().resolve(self._settings.source_key)
        return source.key if source is not None else DEFAULT_MIC_KEY

    def source_label(self) -> str:
        source = self.sources().resolve(self._settings.source_key)
        return source.label if source is not None else "Microphone"

    def select_source(self, key: str) -> None:
        if key == self._settings.source_key:
            return
        self._settings = replace(self._settings, source_key=key)
        try:
            self._store.save(self._settings)
        except OSError:
            log.warning("Could not persist the selected source", exc_info=True)
        self.source_changed.emit(key)

    def preflight(self) -> None:
        """Surface a missing ffmpeg at startup instead of on the first run."""
        if not self._ffmpeg_check():
            self._machine.fail(ErrorKind.FFMPEG_MISSING)

    def toggle(self) -> None:
        if self.state.active:
            self.cancel()
        else:
            self.start()

    def start(self) -> None:
        """Begin a run; ignored while a previous thread is still running."""
        if self._thread is not None or self.state.active:
            return
        if not self._ffmpeg_check():
            self._machine.fail(ErrorKind.FFMPEG_MISSING)
            return
        source = self.sources().resolve(self._settings.source_key)
        if source is None or not source.available:
            self._machine.fail(ErrorKind.SOURCE_UNAVAILABLE)
            return

        thread = RecognitionThread(self._pipeline, source, parent=self)
        thread.phase_changed.connect(self._on_phase)
        thread.level_changed.connect(self.level_changed)
        thread.succeeded.connect(self._on_succeeded)
        thread.failed.connect(self._on_failed)
        thread.finished.connect(self._on_thread_finished)
        self._thread = thread
        self._machine.begin()
        thread.start()

    def cancel(self) -> None:
        if self._thread is not None:
            self._thread.cancel()
        if self.state.active:
            self._machine.cancel()

    def shutdown(self) -> None:
        """Cancel any run and wait for the worker thread before the app exits."""
        self.cancel()
        if self._thread is not None:
            self._thread.wait(3000)

    @Slot(object)
    def _on_phase(self, phase: Phase) -> None:
        if self.state.active:
            self._machine.advance(phase)

    @Slot(object)
    def _on_succeeded(self, track: Track) -> None:
        if self.state.active:
            self._machine.succeed(track)

    @Slot(object)
    def _on_failed(self, kind: ErrorKind) -> None:
        if self.state.active:
            self._machine.fail(kind)

    @Slot()
    def _on_thread_finished(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.deleteLater()
