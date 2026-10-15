"""System accessibility preferences that change how the window is drawn."""

from __future__ import annotations

import sys
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SystemPreferences:
    reduce_transparency: bool = False
    reduce_motion: bool = False


def read_system_preferences() -> SystemPreferences:
    """Read Reduce Transparency and Reduce Motion from the OS; defaults elsewhere."""
    if sys.platform == "darwin":
        return _read_macos()
    if sys.platform == "win32":
        return _read_windows()
    return SystemPreferences()


def _read_macos() -> SystemPreferences:
    if sys.platform != "darwin":
        return SystemPreferences()
    try:
        from AppKit import NSWorkspace
    except ImportError:
        return SystemPreferences()
    workspace = NSWorkspace.sharedWorkspace()
    return SystemPreferences(
        reduce_transparency=bool(workspace.accessibilityDisplayShouldReduceTransparency()),
        reduce_motion=bool(workspace.accessibilityDisplayShouldReduceMotion()),
    )


def _read_windows() -> SystemPreferences:
    if sys.platform != "win32":
        return SystemPreferences()
    import ctypes
    import winreg

    reduce_transparency = False
    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            enabled, _ = winreg.QueryValueEx(key, "EnableTransparency")
            reduce_transparency = enabled == 0
    except OSError:
        pass

    spi_getclientareaanimation = 0x1042
    animations = ctypes.c_int(1)
    ctypes.windll.user32.SystemParametersInfoW(
        spi_getclientareaanimation, 0, ctypes.byref(animations), 0
    )
    return SystemPreferences(
        reduce_transparency=reduce_transparency,
        reduce_motion=animations.value == 0,
    )
