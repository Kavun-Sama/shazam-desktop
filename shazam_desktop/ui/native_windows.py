"""Windows 11 Acrylic backdrop via DWM (``DWMWA_SYSTEMBACKDROP_TYPE``)."""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

from PySide6.QtWidgets import QWidget

if sys.platform != "win32":
    raise ImportError("native_windows is Windows-only")

log = logging.getLogger(__name__)

_DWMWA_USE_IMMERSIVE_DARK_MODE = 20
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMWCP_DONOTROUND = 1
_DWMSBT_NONE = 1
_DWMSBT_TRANSIENTWINDOW = 3  # Acrylic
_MIN_BUILD = 22621  # first Windows 11 build that honours DWMWA_SYSTEMBACKDROP_TYPE


class _Margins(ctypes.Structure):
    _fields_ = (
        ("left", ctypes.c_int),
        ("right", ctypes.c_int),
        ("top", ctypes.c_int),
        ("bottom", ctypes.c_int),
    )


_dwmapi = ctypes.WinDLL("dwmapi")
_user32 = ctypes.WinDLL("user32")
_gdi32 = ctypes.WinDLL("gdi32")

_dwmapi.DwmSetWindowAttribute.argtypes = [
    wintypes.HWND,
    wintypes.DWORD,
    wintypes.LPCVOID,
    wintypes.DWORD,
]
_dwmapi.DwmSetWindowAttribute.restype = ctypes.c_long
_dwmapi.DwmExtendFrameIntoClientArea.argtypes = [wintypes.HWND, ctypes.POINTER(_Margins)]
_dwmapi.DwmExtendFrameIntoClientArea.restype = ctypes.c_long
_gdi32.CreateRoundRectRgn.argtypes = [ctypes.c_int] * 6
_gdi32.CreateRoundRectRgn.restype = wintypes.HRGN
_user32.SetWindowRgn.argtypes = [wintypes.HWND, wintypes.HRGN, wintypes.BOOL]
_user32.SetWindowRgn.restype = ctypes.c_int


def supported() -> bool:
    return sys.getwindowsversion().build >= _MIN_BUILD


def _set_attribute(hwnd: int, attribute: int, value: int) -> int:
    data = ctypes.c_int(value)
    return int(
        _dwmapi.DwmSetWindowAttribute(hwnd, attribute, ctypes.byref(data), ctypes.sizeof(data))
    )


class WindowsBackdrop:
    """Acrylic behind the whole client area, clipped to a rounded region."""

    def __init__(self, widget: QWidget) -> None:
        self._widget = widget
        self._hwnd = int(widget.winId())
        self._enabled = False
        _set_attribute(self._hwnd, _DWMWA_WINDOW_CORNER_PREFERENCE, _DWMWCP_DONOTROUND)

    def set_enabled(self, enabled: bool) -> bool:
        if enabled == self._enabled:
            return self._enabled
        backdrop = _DWMSBT_TRANSIENTWINDOW if enabled else _DWMSBT_NONE
        result = _set_attribute(self._hwnd, _DWMWA_SYSTEMBACKDROP_TYPE, backdrop)
        if enabled and result != 0:
            log.warning(
                "DwmSetWindowAttribute(SYSTEMBACKDROP_TYPE) failed: 0x%08X", result & 0xFFFFFFFF
            )
            return False
        margin = -1 if enabled else 0
        _dwmapi.DwmExtendFrameIntoClientArea(
            self._hwnd, ctypes.byref(_Margins(margin, margin, margin, margin))
        )
        if not enabled:
            _user32.SetWindowRgn(self._hwnd, None, True)
        self._enabled = enabled
        return enabled

    def set_dark(self, dark: bool) -> None:
        _set_attribute(self._hwnd, _DWMWA_USE_IMMERSIVE_DARK_MODE, int(dark))

    def update_shape(self, width: float, height: float, radius: float) -> None:
        if not self._enabled:
            return
        ratio = self._widget.devicePixelRatioF()
        diameter = round(2 * radius * ratio)
        region = _gdi32.CreateRoundRectRgn(
            0, 0, round(width * ratio) + 1, round(height * ratio) + 1, diameter, diameter
        )
        _user32.SetWindowRgn(self._hwnd, region, True)
