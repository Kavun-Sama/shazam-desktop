"""Settings model and its JSON store."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

import platformdirs

from shazam_desktop.audio.sources import DEFAULT_MIC_KEY
from shazam_desktop.settings.hotkey import Hotkey, default_hotkey, parse_hotkey

log = logging.getLogger(__name__)

APP_NAME = "shazam-desktop"


@dataclass(frozen=True, slots=True)
class Settings:
    source_key: str = DEFAULT_MIC_KEY
    hotkey: Hotkey = field(default_factory=default_hotkey)


class SettingsStore:
    """Reads and writes :class:`Settings` as a small JSON file."""

    def __init__(self, path: Path) -> None:
        self._path = path

    @staticmethod
    def default_path() -> Path:
        return platformdirs.user_config_path(APP_NAME, appauthor=False) / "config.json"

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> Settings:
        """Load settings, falling back to defaults field by field on any problem."""
        defaults = Settings()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return defaults
        except (OSError, ValueError) as exc:
            log.warning("Ignoring unreadable config %s: %s", self._path, exc)
            return defaults
        if not isinstance(raw, dict):
            log.warning("Ignoring config %s: expected a JSON object", self._path)
            return defaults

        source = raw.get("source")
        source_key = source if isinstance(source, str) and source else defaults.source_key

        hotkey = defaults.hotkey
        hotkey_text = raw.get("hotkey")
        if hotkey_text is not None:
            try:
                if not isinstance(hotkey_text, str):
                    raise ValueError("hotkey must be a string")
                hotkey = parse_hotkey(hotkey_text)
            except ValueError as exc:
                log.warning("Invalid hotkey in %s, using %s: %s", self._path, hotkey, exc)
        return Settings(source_key=source_key, hotkey=hotkey)

    def save(self, settings: Settings) -> None:
        """Write settings atomically."""
        payload = {"source": settings.source_key, "hotkey": str(settings.hotkey)}
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, self._path)
