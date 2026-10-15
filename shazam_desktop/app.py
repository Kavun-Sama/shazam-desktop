"""Composition root."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from shazam_desktop.audio.backends import create_backend
from shazam_desktop.controller import Controller
from shazam_desktop.recognition.shazam import ShazamRecognizer
from shazam_desktop.settings.config import SettingsStore
from shazam_desktop.settings.hotkey import Hotkey
from shazam_desktop.ui.app_icon import load_app_icon
from shazam_desktop.ui.hotkey import GlobalHotkey
from shazam_desktop.ui.tray import TrayIcon
from shazam_desktop.ui.window import MainWindow

log = logging.getLogger(__name__)


def run(argv: Sequence[str]) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    app = QApplication(list(argv))
    app.setApplicationName("Shazam Desktop")
    app.setQuitOnLastWindowClosed(False)
    if (icon := load_app_icon()) is not None:
        app.setWindowIcon(icon)

    controller = Controller(
        create_backend(), ShazamRecognizer(), SettingsStore(SettingsStore.default_path())
    )
    window = MainWindow(controller)

    tray: TrayIcon | None = None
    if QSystemTrayIcon.isSystemTrayAvailable():
        tray = TrayIcon(controller, window)
        tray.show()
    else:
        log.warning("No system tray available; quit with Ctrl+Q while the window is focused")

    hotkey = GlobalHotkey(controller.settings.hotkey)
    hotkey.triggered.connect(
        lambda: _on_hotkey(controller, window), Qt.ConnectionType.QueuedConnection
    )
    if not hotkey.start():
        _report_hotkey_failure(tray, controller.settings.hotkey)

    app.aboutToQuit.connect(hotkey.stop)
    app.aboutToQuit.connect(controller.shutdown)

    controller.preflight()
    window.present()
    exit_code = app.exec()
    del tray
    return exit_code


def _on_hotkey(controller: Controller, window: MainWindow) -> None:
    """Show the window and start; pressing again while busy cancels."""
    if controller.state.active:
        controller.cancel()
        return
    window.present()
    controller.start()


def _report_hotkey_failure(tray: TrayIcon | None, hotkey: Hotkey) -> None:
    message = f"{hotkey} is unavailable: another app may be using it. Change it in the config."
    log.warning(message)
    if tray is not None:
        tray.showMessage("Shazam Desktop", message, QSystemTrayIcon.MessageIcon.Warning, 8000)
