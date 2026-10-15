from __future__ import annotations

from pathlib import Path

import pytest

from shazam_desktop.audio.sources import DEFAULT_MIC_KEY, SYSTEM_KEY
from shazam_desktop.settings.config import Settings, SettingsStore
from shazam_desktop.settings.hotkey import default_hotkey, parse_hotkey


@pytest.fixture
def store(tmp_path: Path) -> SettingsStore:
    return SettingsStore(tmp_path / "nested" / "config.json")


def test_missing_file_yields_defaults(store: SettingsStore) -> None:
    assert store.load() == Settings(source_key=DEFAULT_MIC_KEY, hotkey=default_hotkey())


def test_selection_survives_a_restart(store: SettingsStore) -> None:
    store.save(Settings(source_key=SYSTEM_KEY, hotkey=parse_hotkey("alt+shift+m")))
    reloaded = SettingsStore(store.path).load()
    assert reloaded == Settings(source_key=SYSTEM_KEY, hotkey=parse_hotkey("alt+shift+m"))


def test_save_creates_parent_directories_and_leaves_no_temp_file(store: SettingsStore) -> None:
    store.save(Settings())
    assert store.path.is_file()
    assert [p.name for p in store.path.parent.iterdir()] == ["config.json"]


def test_hand_edited_hotkey_is_honoured(store: SettingsStore) -> None:
    store.path.parent.mkdir(parents=True)
    store.path.write_text('{"source": "mic:USB Mic", "hotkey": "Ctrl+Alt+R"}', encoding="utf-8")
    assert store.load() == Settings(source_key="mic:USB Mic", hotkey=parse_hotkey("ctrl+alt+r"))


def test_invalid_hotkey_falls_back_without_losing_the_source(store: SettingsStore) -> None:
    store.path.parent.mkdir(parents=True)
    store.path.write_text('{"source": "system", "hotkey": "banana"}', encoding="utf-8")
    assert store.load() == Settings(source_key="system", hotkey=default_hotkey())


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '"text"', "", '{"source": 3, "hotkey": 7}', '{"source": ""}'],
)
def test_corrupt_content_yields_defaults(store: SettingsStore, content: str) -> None:
    store.path.parent.mkdir(parents=True)
    store.path.write_text(content, encoding="utf-8")
    assert store.load() == Settings()


def test_default_path_is_inside_a_user_config_directory() -> None:
    path = SettingsStore.default_path()
    assert path.name == "config.json"
    assert "shazam-desktop" in path.parts
