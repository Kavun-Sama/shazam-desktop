"""Colors and typography; follows the system light/dark scheme and accent."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtGui import QColor, QFont, QFontDatabase

BODY_PIXEL_SIZE = 13


def _rgba(red: int, green: int, blue: int, alpha: float = 1.0) -> QColor:
    color = QColor(red, green, blue)
    color.setAlphaF(alpha)
    return color


@dataclass(frozen=True, slots=True)
class Theme:
    dark: bool
    text: QColor
    text_secondary: QColor
    accent: QColor
    warning: QColor
    success: QColor
    hover: QColor
    pressed: QColor
    hairline: QColor
    tint: QColor
    translucent_fill: QColor
    opaque_fill: QColor
    stroke_start: QColor
    stroke_end: QColor
    specular: QColor
    shadow: QColor


def build_theme(dark: bool, accent: QColor) -> Theme:
    """Return the palette for the given scheme and system accent color."""
    if dark:
        return Theme(
            dark=True,
            text=_rgba(255, 255, 255, 0.92),
            text_secondary=_rgba(235, 235, 245, 0.60),
            accent=accent,
            warning=_rgba(255, 159, 10),
            success=_rgba(48, 209, 88),
            hover=_rgba(255, 255, 255, 0.10),
            pressed=_rgba(255, 255, 255, 0.16),
            hairline=_rgba(255, 255, 255, 0.14),
            tint=_rgba(255, 255, 255, 0.05),
            translucent_fill=_rgba(40, 40, 44, 0.74),
            opaque_fill=_rgba(44, 44, 46),
            stroke_start=_rgba(255, 255, 255, 0.50),
            stroke_end=_rgba(255, 255, 255, 0.10),
            specular=_rgba(255, 255, 255, 0.20),
            shadow=_rgba(0, 0, 0, 0.60),
        )
    return Theme(
        dark=False,
        text=_rgba(0, 0, 0, 0.88),
        text_secondary=_rgba(60, 60, 67, 0.62),
        accent=accent,
        warning=_rgba(255, 149, 0),
        success=_rgba(52, 199, 89),
        hover=_rgba(0, 0, 0, 0.06),
        pressed=_rgba(0, 0, 0, 0.10),
        hairline=_rgba(0, 0, 0, 0.10),
        tint=_rgba(255, 255, 255, 0.28),
        translucent_fill=_rgba(248, 248, 250, 0.78),
        opaque_fill=_rgba(246, 246, 248),
        stroke_start=_rgba(255, 255, 255, 0.95),
        stroke_end=_rgba(0, 0, 0, 0.10),
        specular=_rgba(255, 255, 255, 0.70),
        shadow=_rgba(0, 0, 0, 0.32),
    )


def system_font(weight: QFont.Weight = QFont.Weight.Normal) -> QFont:
    """The platform UI font (SF on macOS, Segoe UI Variable on Windows) at the single body size."""
    font = QFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    if sys.platform == "win32":
        font.setFamilies(["Segoe UI Variable Text", "Segoe UI"])
    font.setPixelSize(BODY_PIXEL_SIZE)
    font.setWeight(weight)
    return font
