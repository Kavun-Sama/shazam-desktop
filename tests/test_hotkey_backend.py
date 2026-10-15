"""Windows ``RegisterHotKey`` backend against a fake ``user32``, and signal delivery."""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections.abc import Callable
from typing import Any

import pytest
from PySide6.QtCore import QEventLoop, Qt

from shazam_desktop.settings.hotkey import Hotkey, parse_hotkey
from shazam_desktop.ui.hotkey import GlobalHotkey
from shazam_desktop.ui.hotkey_windows import Win32HotkeyBackend, win32_parameters

MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
VK_1 = 0x31
ERROR_HOTKEY_ALREADY_REGISTERED = 1409


class FakeUser32:
    """Just enough of ``user32`` for the hotkey message loop."""

    def __init__(self, *, can_register: bool = True) -> None:
        self.can_register = can_register
        self.registered: list[tuple[int, int]] = []
        self.unregistered = threading.Event()
        self.thread_ids: list[int] = []
        self._messages: queue.Queue[tuple[int, int] | None] = queue.Queue()

    def press(self, hotkey_id: int = 1) -> None:
        self._messages.put((WM_HOTKEY, hotkey_id))

    def PeekMessageW(self, *_args: Any) -> int:
        return 0

    def RegisterHotKey(self, _hwnd: Any, _hotkey_id: int, modifiers: int, vk: int) -> int:
        self.registered.append((modifiers, vk))
        return int(self.can_register)

    def UnregisterHotKey(self, *_args: Any) -> int:
        self.unregistered.set()
        return 1

    def GetMessageW(self, message: Any, *_args: Any) -> int:
        item = self._messages.get(timeout=5)
        if item is None:
            return 0
        message._obj.message, message._obj.wParam = item
        return 1

    def PostThreadMessageW(self, thread_id: int, message: int, *_args: Any) -> int:
        self.thread_ids.append(thread_id)
        if message == WM_QUIT:
            self._messages.put(None)
        return 1


def wait_for(condition: Callable[[], bool], timeout: float = 2.0) -> None:
    deadline = time.monotonic() + timeout
    while not condition():
        if time.monotonic() > deadline:
            raise AssertionError("condition not reached in time")
        time.sleep(0.005)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ctrl+shift+1", (MOD_CONTROL | MOD_SHIFT, 0x31)),
        ("ctrl+alt+s", (MOD_CONTROL | 0x0001, 0x53)),
        ("cmd+space", (0x0008, 0x20)),
        ("shift+f5", (MOD_SHIFT, 0x74)),
        ("ctrl+f12", (MOD_CONTROL, 0x7B)),
        ("alt+page_up", (0x0001, 0x21)),
    ],
)
def test_win32_parameters(text: str, expected: tuple[int, int]) -> None:
    assert win32_parameters(parse_hotkey(text)) == expected


def test_win32_parameters_ignore_the_keyboard_layout() -> None:
    # The same virtual key serves the Latin "s" and the Cyrillic "ы" layouts.
    assert win32_parameters(parse_hotkey("ctrl+s"))[1] == ord("S")


def test_win32_parameters_reject_keys_without_a_virtual_key() -> None:
    with pytest.raises(ValueError, match="virtual-key"):
        win32_parameters(Hotkey(frozenset({"ctrl"}), "й"))


def test_registers_without_auto_repeat_and_calls_back_on_wm_hotkey() -> None:
    user32 = FakeUser32()
    backend = Win32HotkeyBackend(user32)
    pressed = threading.Event()

    assert backend.start(parse_hotkey("ctrl+shift+1"), pressed.set)
    assert user32.registered == [(MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT, VK_1)]

    user32.press(hotkey_id=99)  # someone else's hotkey id
    assert not pressed.wait(0.05)
    user32.press()
    assert pressed.wait(2)
    backend.stop()


def test_stop_unregisters_and_ends_the_thread() -> None:
    user32 = FakeUser32()
    backend = Win32HotkeyBackend(user32)
    assert backend.start(parse_hotkey("ctrl+shift+1"), lambda: None)

    backend.stop()

    assert user32.unregistered.is_set()
    assert user32.thread_ids == [user32.thread_ids[0]] != [0]
    assert not [t for t in threading.enumerate() if t.name == "hotkey"]


def test_registration_conflict_is_reported_and_leaves_no_thread() -> None:
    user32 = FakeUser32(can_register=False)
    backend = Win32HotkeyBackend(user32, last_error=lambda: ERROR_HOTKEY_ALREADY_REGISTERED)

    assert not backend.start(parse_hotkey("ctrl+shift+1"), lambda: None)

    assert backend.error == ERROR_HOTKEY_ALREADY_REGISTERED
    assert not [t for t in threading.enumerate() if t.name == "hotkey"]


def test_starting_twice_is_a_programming_error() -> None:
    backend = Win32HotkeyBackend(FakeUser32())
    assert backend.start(parse_hotkey("ctrl+shift+1"), lambda: None)
    try:
        with pytest.raises(RuntimeError, match="already running"):
            backend.start(parse_hotkey("ctrl+shift+1"), lambda: None)
    finally:
        backend.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="registers a real hotkey on Windows")
def test_backend_unavailable_off_windows_is_a_failed_start_not_a_crash() -> None:
    assert not Win32HotkeyBackend().start(parse_hotkey("ctrl+shift+1"), lambda: None)


class ThreadedBackend:
    """Fires the callback from a foreign thread, like both real backends do."""

    def __init__(self) -> None:
        self.fired = threading.Event()

    def start(self, hotkey: Hotkey, callback: Callable[[], None]) -> bool:
        def fire() -> None:
            callback()
            self.fired.set()

        threading.Thread(target=fire, daemon=True).start()
        return True

    def stop(self) -> None: ...


def test_signal_is_delivered_on_the_gui_thread(qapp: Any) -> None:
    backend = ThreadedBackend()
    hotkey = GlobalHotkey(parse_hotkey("ctrl+shift+1"), backend=backend)
    delivered_on: list[int] = []
    hotkey.triggered.connect(
        lambda: delivered_on.append(threading.get_ident()), Qt.ConnectionType.QueuedConnection
    )

    assert hotkey.start()
    assert backend.fired.wait(2)
    wait_for(
        lambda: (
            qapp.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 10),
            bool(delivered_on),
        )[1]
    )

    assert delivered_on == [threading.get_ident()]
