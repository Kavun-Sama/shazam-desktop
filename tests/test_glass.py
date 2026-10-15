"""The native backdrop must never touch a window handle owned by a non-native Qt plugin."""

from __future__ import annotations

import sys
from typing import Any

import pytest
from PySide6.QtWidgets import QWidget

from shazam_desktop.ui import glass


def test_no_backdrop_on_a_non_native_qt_platform(
    qapp: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(sys, "platform", "darwin")

    def fail(*args: object) -> None:
        raise AssertionError("winId() must not be read on the offscreen platform")

    monkeypatch.setattr(QWidget, "winId", fail)
    assert glass.create_backdrop(QWidget()) is None
