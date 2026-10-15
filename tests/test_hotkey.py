from __future__ import annotations

import pytest

from shazam_desktop.settings.hotkey import Hotkey, default_hotkey, parse_hotkey


def test_parses_canonical_form() -> None:
    assert parse_hotkey("ctrl+shift+s") == Hotkey(frozenset({"ctrl", "shift"}), "s")


def test_is_case_and_space_insensitive_and_accepts_aliases() -> None:
    assert parse_hotkey(" Control + SHIFT + S ") == parse_hotkey("ctrl+shift+s")
    assert parse_hotkey("Command+Option+F5") == Hotkey(frozenset({"cmd", "alt"}), "f5")


def test_str_is_canonical_and_modifier_order_is_stable() -> None:
    assert str(parse_hotkey("shift+cmd+ctrl+alt+k")) == "ctrl+alt+shift+cmd+k"


def test_round_trips_through_str() -> None:
    hotkey = parse_hotkey("alt+space")
    assert parse_hotkey(str(hotkey)) == hotkey


def test_pynput_notation() -> None:
    assert parse_hotkey("ctrl+shift+s").to_pynput() == "<ctrl>+<shift>+s"
    assert parse_hotkey("cmd+f12").to_pynput() == "<cmd>+<f12>"
    assert parse_hotkey("ctrl+alt+page_up").to_pynput() == "<ctrl>+<alt>+<page_up>"


@pytest.mark.parametrize(
    "text",
    ["", "s", "ctrl", "ctrl+", "ctrl+shift", "ctrl+s+d", "ctrl+esc", "ctrl+??", "ctrl+f21"],
)
def test_rejects_invalid_hotkeys(text: str) -> None:
    with pytest.raises(ValueError, match=r"hotkey|key"):
        parse_hotkey(text)


def test_default_depends_on_platform() -> None:
    assert str(default_hotkey("darwin")) == "shift+cmd+1"
    assert str(default_hotkey("win32")) == "ctrl+shift+1"
    assert str(default_hotkey("linux")) == "ctrl+shift+1"
