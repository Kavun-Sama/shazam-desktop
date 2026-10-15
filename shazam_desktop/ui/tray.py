"""Tray / menu-bar icon: show the window, pick the source, quit."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from shazam_desktop.controller import Controller
from shazam_desktop.ui.icons import tray_icon
from shazam_desktop.ui.source_menu import SourceMenu
from shazam_desktop.ui.window import MainWindow


def _icon() -> QIcon:
    if sys.platform == "darwin":
        return tray_icon(QColor("black"), mask=True)
    dark = QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return tray_icon(QColor("white") if dark else QColor("black"))


class TrayIcon(QSystemTrayIcon):
    def __init__(self, controller: Controller, window: MainWindow) -> None:
        super().__init__(_icon())
        self.setToolTip("Shazam Desktop")
        self._window = window

        self._menu = QMenu()
        show = self._menu.addAction("Show")
        show.triggered.connect(window.present)
        self._sources = SourceMenu(controller, self._menu)
        self._sources.setTitle("Source")
        self._sources.aboutToShow.connect(self._sources.refresh)
        self._menu.addMenu(self._sources)
        self._menu.addSeparator()
        quit_action = self._menu.addAction("Quit")
        quit_action.triggered.connect(QApplication.quit)
        self.setContextMenu(self._menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason is QSystemTrayIcon.ActivationReason.Trigger:
            self._window.present()
