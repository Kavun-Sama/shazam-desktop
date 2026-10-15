"""System-wide hotkey on Windows through ``RegisterHotKey``.

The OS matches the hotkey by virtual-key code, so it is independent of the active keyboard
layout and works while any other window has focus. A low-level keyboard hook (what ``pynput``
installs) is layout-dependent and is not delivered when an elevated window is in the foreground.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
from collections.abc import Callable
from ctypes import wintypes
from typing import Any

from shazam_desktop.settings.hotkey import Hotkey

log = logging.getLogger(__name__)

_MOD_ALT = 0x0001
_MOD_CONTROL = 0x0002
_MOD_SHIFT = 0x0004
_MOD_WIN = 0x0008
_MOD_NOREPEAT = 0x4000

_WM_QUIT = 0x0012
_WM_USER = 0x0400
_WM_HOTKEY = 0x0312
_PM_NOREMOVE = 0x0000
_HOTKEY_ID = 1
_ERROR_HOTKEY_ALREADY_REGISTERED = 1409
_START_TIMEOUT = 2.0
_JOIN_TIMEOUT = 2.0

_MODIFIERS = {"ctrl": _MOD_CONTROL, "alt": _MOD_ALT, "shift": _MOD_SHIFT, "cmd": _MOD_WIN}
_NAMED_KEYS = {
    "space": 0x20,
    "enter": 0x0D,
    "tab": 0x09,
    "backspace": 0x08,
    "delete": 0x2E,
    "insert": 0x2D,
    "home": 0x24,
    "end": 0x23,
    "page_up": 0x21,
    "page_down": 0x22,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
}
_FUNCTION_KEY_BASE = 0x70  # VK_F1


def win32_parameters(hotkey: Hotkey) -> tuple[int, int]:
    """Return ``(modifier flags, virtual-key code)`` for ``RegisterHotKey``."""
    modifiers = 0
    for modifier in hotkey.modifiers:
        modifiers |= _MODIFIERS[modifier]

    key = hotkey.key
    if key in _NAMED_KEYS:
        return modifiers, _NAMED_KEYS[key]
    if len(key) > 1 and key.startswith("f") and key[1:].isdigit():
        return modifiers, _FUNCTION_KEY_BASE + int(key[1:]) - 1
    if len(key) == 1 and key.isascii() and key.isalnum():
        return modifiers, ord(key.upper())  # VK codes of 0-9 and A-Z equal their ASCII codes
    raise ValueError(f"key {key!r} has no Windows virtual-key code")


def _load_user32() -> Any:
    if sys.platform != "win32":
        raise OSError("RegisterHotKey is only available on Windows")
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    user32.RegisterHotKey.restype = wintypes.BOOL
    user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.UnregisterHotKey.restype = wintypes.BOOL
    user32.GetMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.GetMessageW.restype = wintypes.BOOL
    user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG),
        wintypes.HWND,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.UINT,
    ]
    user32.PeekMessageW.restype = wintypes.BOOL
    user32.PostThreadMessageW.argtypes = [
        wintypes.DWORD,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostThreadMessageW.restype = wintypes.BOOL
    return user32


def _win32_last_error() -> int:
    if sys.platform != "win32":
        return 0
    return int(ctypes.get_last_error())


class Win32HotkeyBackend:
    """Registers the hotkey on a private thread that pumps its own message queue.

    ``RegisterHotKey`` is bound to the registering thread, which must also retrieve the
    ``WM_HOTKEY`` messages, hence the dedicated thread. ``user32`` and ``last_error`` are
    injectable so the message loop can be exercised without Windows.
    """

    def __init__(
        self,
        user32: Any | None = None,
        last_error: Callable[[], int] | None = None,
    ) -> None:
        self._user32 = user32
        self._last_error = last_error or _win32_last_error
        self._thread: threading.Thread | None = None
        self._thread_id = 0
        self._error = 0

    @property
    def error(self) -> int:
        """Win32 error code of the last failed registration, 0 when it succeeded."""
        return self._error

    def start(self, hotkey: Hotkey, callback: Callable[[], None]) -> bool:
        if self._thread is not None:
            raise RuntimeError("hotkey backend is already running")
        try:
            modifiers, vk = win32_parameters(hotkey)
            user32 = self._user32 or _load_user32()
        except (ValueError, OSError):
            log.warning("Hotkey %s cannot be registered", hotkey, exc_info=True)
            return False

        ready = threading.Event()
        thread = threading.Thread(
            target=self._run,
            args=(user32, modifiers | _MOD_NOREPEAT, vk, callback, ready),
            name="hotkey",
            daemon=True,
        )
        thread.start()
        if not ready.wait(_START_TIMEOUT) or self._error:
            if self._error == _ERROR_HOTKEY_ALREADY_REGISTERED:
                log.warning("Hotkey %s is already registered by another application", hotkey)
            else:
                log.warning("RegisterHotKey failed for %s (error %d)", hotkey, self._error)
            self._finish(user32, thread)
            return False
        self._thread = thread
        self._user32 = user32
        return True

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None and self._user32 is not None:
            self._finish(self._user32, thread)

    def _finish(self, user32: Any, thread: threading.Thread) -> None:
        if thread.is_alive() and self._thread_id:
            user32.PostThreadMessageW(self._thread_id, _WM_QUIT, 0, 0)
        thread.join(_JOIN_TIMEOUT)

    def _run(
        self,
        user32: Any,
        modifiers: int,
        vk: int,
        callback: Callable[[], None],
        ready: threading.Event,
    ) -> None:
        message = wintypes.MSG()
        # Touching the queue creates it, so a WM_QUIT posted right after start is not lost.
        user32.PeekMessageW(ctypes.byref(message), None, _WM_USER, _WM_USER, _PM_NOREMOVE)
        self._thread_id = threading.get_native_id()  # equals GetCurrentThreadId on Windows
        registered = bool(user32.RegisterHotKey(None, _HOTKEY_ID, modifiers, vk))
        self._error = 0 if registered else self._last_error()
        ready.set()
        if not registered:
            return
        try:
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                if message.message == _WM_HOTKEY and message.wParam == _HOTKEY_ID:
                    callback()
        finally:
            user32.UnregisterHotKey(None, _HOTKEY_ID)
