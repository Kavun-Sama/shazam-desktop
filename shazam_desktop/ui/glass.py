"""Native backdrop blur behind the window, with a graceful "not available" answer."""

from __future__ import annotations

import logging
import sys
from typing import Protocol

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

log = logging.getLogger(__name__)


class NativeBackdrop(Protocol):
    """A system material (Acrylic / NSVisualEffectView) attached to a top-level window."""

    def set_enabled(self, enabled: bool) -> bool:
        """Show or hide the material; returns whether it is now visible."""
        ...

    def set_dark(self, dark: bool) -> None: ...

    def update_shape(self, width: float, height: float, radius: float) -> None:
        """Clip the material to a rounded rectangle (logical pixels)."""
        ...


_NATIVE_QPA = {"win32": "windows", "darwin": "cocoa"}


def create_backdrop(widget: QWidget) -> NativeBackdrop | None:
    """Attach the platform material to ``widget``'s native window, or return ``None``."""
    # Only the platform's own Qt plugin hands out real HWND / NSView handles for winId();
    # offscreen and similar plugins return opaque ids that must not be dereferenced.
    if QGuiApplication.platformName() != _NATIVE_QPA.get(sys.platform):
        return None
    try:
        if sys.platform == "win32":
            from shazam_desktop.ui import native_windows

            if native_windows.supported():
                return native_windows.WindowsBackdrop(widget)
        elif sys.platform == "darwin":
            from shazam_desktop.ui import native_macos

            return native_macos.MacBackdrop(widget)
    except Exception:
        # Native bridges (ctypes / pyobjc) can fail in many platform-specific ways;
        # the translucent fallback is always acceptable.
        log.warning("Native backdrop unavailable, using the translucent fallback", exc_info=True)
    return None
