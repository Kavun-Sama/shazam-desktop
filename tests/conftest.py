"""Shared fixtures; Qt runs on the offscreen platform so tests need no display."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture
def match_response() -> dict[str, Any]:
    return load_fixture("shazam_match.json")


@pytest.fixture
def no_match_response() -> dict[str, Any]:
    return load_fixture("shazam_no_match.json")


@pytest.fixture(scope="session")
def qapp() -> Any:
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])
