"""Hotkey notation used in the config file, e.g. ``ctrl+shift+1``."""

from __future__ import annotations

import sys
from dataclasses import dataclass

_MODIFIER_ALIASES = {
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "option": "alt",
    "opt": "alt",
    "shift": "shift",
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "win": "cmd",
    "meta": "cmd",
}
_MODIFIER_ORDER = ("ctrl", "alt", "shift", "cmd")
_NAMED_KEYS = frozenset(
    {
        "space",
        "enter",
        "tab",
        "backspace",
        "delete",
        "insert",
        "home",
        "end",
        "page_up",
        "page_down",
        "up",
        "down",
        "left",
        "right",
        *(f"f{number}" for number in range(1, 21)),
    }
)


@dataclass(frozen=True, slots=True)
class Hotkey:
    modifiers: frozenset[str]
    key: str

    def __str__(self) -> str:
        return "+".join([*self._ordered_modifiers(), self.key])

    def to_pynput(self) -> str:
        """Render in the notation ``pynput.keyboard.GlobalHotKeys`` expects."""
        parts = [f"<{modifier}>" for modifier in self._ordered_modifiers()]
        parts.append(f"<{self.key}>" if len(self.key) > 1 else self.key)
        return "+".join(parts)

    def _ordered_modifiers(self) -> list[str]:
        return sorted(self.modifiers, key=_MODIFIER_ORDER.index)


def parse_hotkey(text: str) -> Hotkey:
    """Parse ``"Ctrl+Shift+S"``-style text; raises :class:`ValueError` when invalid."""
    modifiers: set[str] = set()
    keys: list[str] = []
    for token in (part.strip().lower() for part in text.split("+")):
        if token in _MODIFIER_ALIASES:
            modifiers.add(_MODIFIER_ALIASES[token])
        elif (len(token) == 1 and token.isalnum()) or token in _NAMED_KEYS:
            keys.append(token)
        else:
            raise ValueError(f"unsupported key {token!r} in hotkey {text!r}")
    if len(keys) != 1:
        raise ValueError(f"hotkey {text!r} needs exactly one non-modifier key")
    if not modifiers:
        raise ValueError(f"hotkey {text!r} needs at least one modifier")
    return Hotkey(frozenset(modifiers), keys[0])


def default_hotkey(platform: str = sys.platform) -> Hotkey:
    """Ctrl+Shift+1, or Cmd+Shift+1 on macOS."""
    return Hotkey(frozenset({"cmd" if platform == "darwin" else "ctrl", "shift"}), "1")
