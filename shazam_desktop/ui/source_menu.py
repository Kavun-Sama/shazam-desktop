"""Source menu: Microphone, every input device, System Audio; built from what is found."""

from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QWidget

from shazam_desktop.audio.sources import AudioSource, SourceKind
from shazam_desktop.controller import Controller


class SourceMenu(QMenu):
    """Rebuilds itself from the live device list on :meth:`refresh`."""

    def __init__(self, controller: Controller, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self.setToolTipsVisible(True)

    def refresh(self) -> None:
        self.clear()
        catalog = self._controller.sources()
        current = self._controller.source_key()

        microphones = catalog.microphones
        if microphones:
            self._add_source(microphones[0], current)
            if len(microphones) > 1:
                self.addSeparator()
                for source in microphones[1:]:
                    self._add_source(source, current)

        system = catalog.system
        if system is not None:
            self.addSeparator()
            self._add_source(system, current)
            if not system.available and system.hint:
                hint = self.addAction(system.hint)
                hint.setEnabled(False)

    def _add_source(self, source: AudioSource, current: str) -> QAction:
        action = self.addAction(source.label)
        action.setCheckable(True)
        action.setChecked(source.key == current)
        action.setEnabled(source.available)
        if source.hint:
            action.setToolTip(source.hint)
        elif source.kind is SourceKind.MICROPHONE:
            action.setToolTip(source.label)
        action.triggered.connect(lambda _checked=False, key=source.key: self._select(key))
        return action

    def _select(self, key: str) -> None:
        self._controller.select_source(key)
