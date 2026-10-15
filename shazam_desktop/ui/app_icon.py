"""The application icon shown on windows and the taskbar."""

from __future__ import annotations

from PySide6.QtGui import QIcon

from shazam_desktop.runtime import app_icon_path


def load_app_icon() -> QIcon | None:
    """Load the bundled multi-size icon; ``None`` when it is missing or unreadable."""
    path = app_icon_path()
    if path is None:
        return None
    icon = QIcon(str(path))
    return None if icon.isNull() or not icon.availableSizes() else icon
