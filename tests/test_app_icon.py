from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from shazam_desktop.ui.app_icon import load_app_icon


def test_the_bundled_icon_loads_with_several_sizes(qapp: QApplication) -> None:
    icon = load_app_icon()
    assert icon is not None
    assert len(icon.availableSizes()) >= 4
    assert not icon.pixmap(32, 32).isNull()
