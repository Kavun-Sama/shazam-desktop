from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from shazam_desktop.runtime import bundled_tools_dir, is_frozen, prepend_bundled_tools_to_path


@pytest.fixture
def bundle(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A fake PyInstaller bundle with an ``ffmpeg`` directory."""
    (tmp_path / "ffmpeg").mkdir()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    return tmp_path / "ffmpeg"


def test_not_frozen_by_default() -> None:
    assert not is_frozen()
    assert bundled_tools_dir() is None


def test_finds_the_tools_directory_in_a_bundle(bundle: Path) -> None:
    assert is_frozen()
    assert bundled_tools_dir() == bundle


def test_bundle_without_the_directory_has_no_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert bundled_tools_dir() is None


def test_prepends_to_path_keeping_the_rest(bundle: Path) -> None:
    environ = {"PATH": os.pathsep.join(["/usr/bin", "/bin"])}

    assert prepend_bundled_tools_to_path(environ) == bundle

    assert environ["PATH"].split(os.pathsep) == [str(bundle), "/usr/bin", "/bin"]


def test_prepends_to_an_empty_path_without_a_trailing_separator(bundle: Path) -> None:
    environ: dict[str, str] = {}
    prepend_bundled_tools_to_path(environ)
    assert environ["PATH"] == str(bundle)


def test_leaves_path_alone_outside_a_bundle() -> None:
    environ = {"PATH": "/usr/bin"}
    assert prepend_bundled_tools_to_path(environ) is None
    assert environ == {"PATH": "/usr/bin"}
