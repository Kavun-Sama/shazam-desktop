"""Qt thread that runs one recognition pipeline pass off the GUI thread."""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, QThread, Signal

from shazam_desktop.audio.sources import AudioSource
from shazam_desktop.errors import CancelledError, ErrorKind, RecognitionError
from shazam_desktop.recognition.pipeline import Pipeline, PipelineCallbacks

log = logging.getLogger(__name__)


class RecognitionThread(QThread):
    """Runs a single :meth:`Pipeline.run` and reports the outcome through signals."""

    phase_changed = Signal(object)
    level_changed = Signal(float)
    succeeded = Signal(object)
    failed = Signal(object)
    cancelled = Signal()

    def __init__(
        self,
        pipeline: Pipeline,
        source: AudioSource,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._pipeline = pipeline
        self._source = source
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def run(self) -> None:
        callbacks = PipelineCallbacks(
            on_phase=self.phase_changed.emit,
            on_level=self.level_changed.emit,
        )
        try:
            track = self._pipeline.run(self._source, self._cancel, callbacks)
        except CancelledError:
            self.cancelled.emit()
        except RecognitionError as exc:
            self.failed.emit(exc.kind)
        except Exception:
            log.exception("Recognition run crashed")
            self.failed.emit(ErrorKind.UNEXPECTED)
        else:
            self.succeeded.emit(track)
