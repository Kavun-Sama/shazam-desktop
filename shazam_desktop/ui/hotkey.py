"""System-wide hotkey, delivered to the GUI thread as a Qt signal."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from typing import Any, Protocol

from PySide6.QtCore import QObject, Signal

from shazam_desktop.settings.hotkey import Hotkey

log = logging.getLogger(__name__)


class HotkeyBackend(Protocol):
    """Platform mechanism that calls ``callback`` (from any thread) when the hotkey is pressed."""

    def start(self, hotkey: Hotkey, callback: Callable[[], None]) -> bool: ...

    def stop(self) -> None: ...


class PynputBackend:
    """Keyboard-hook based backend for macOS and Linux.

    ``pynput`` is imported lazily: on platforms without a usable input backend
    (e.g. a Linux box without X) importing it fails, and the app must keep working.
    """

    def __init__(self) -> None:
        self._listener: Any = None

    def start(self, hotkey: Hotkey, callback: Callable[[], None]) -> bool:
        try:
            from pynput import keyboard

            listener = keyboard.GlobalHotKeys({hotkey.to_pynput(): callback})
            listener.start()
        except Exception:
            log.warning("Global hotkey %s is unavailable", hotkey, exc_info=True)
            return False
        self._listener = listener
        return True

    def stop(self) -> None:
        listener, self._listener = self._listener, None
        if listener is not None:
            listener.stop()


def create_backend(platform: str = sys.platform) -> HotkeyBackend:
    if platform == "win32":
        from shazam_desktop.ui.hotkey_windows import Win32HotkeyBackend

        return Win32HotkeyBackend()
    return PynputBackend()


class GlobalHotkey(QObject):
    """One system-wide key combination; :attr:`triggered` fires on the GUI thread."""

    triggered = Signal()

    def __init__(
        self,
        hotkey: Hotkey,
        parent: QObject | None = None,
        *,
        backend: HotkeyBackend | None = None,
    ) -> None:
        super().__init__(parent)
        self._hotkey = hotkey
        self._backend = backend or create_backend()

    def start(self) -> bool:
        """Start listening; returns ``False`` when the hotkey could not be registered."""
        return self._backend.start(self._hotkey, self._emit)

    def stop(self) -> None:
        self._backend.stop()

    def _emit(self) -> None:
        # Runs on the backend's thread; Qt queues the delivery to this object's thread.
        self.triggered.emit()
