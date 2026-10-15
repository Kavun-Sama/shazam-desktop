"""Painting of the glass surface: tint, gradient stroke, specular edge and soft shadow."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen

from shazam_desktop.ui.theme import Theme

SHADOW_MARGIN = 20
_SHADOW_STEPS = 10
_SHADOW_SPREAD = 14.0
_SHADOW_OFFSET = 4.0
_SPECULAR_DEPTH = 36.0


class SurfaceMode(Enum):
    NATIVE = auto()  # OS blur behind the window; only a light tint is painted
    TRANSLUCENT = auto()  # no native blur: tinted translucent fill
    OPAQUE = auto()  # Reduce Transparency: solid material


def paint_surface(
    painter: QPainter, body: QRectF, radius: float, theme: Theme, mode: SurfaceMode
) -> None:
    """Paint the glass body into ``body`` (the window rect minus any shadow margin)."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = QPainterPath()
    shape.addRoundedRect(body, radius, radius)

    if mode is not SurfaceMode.NATIVE:
        _paint_shadow(painter, body, radius, shape, theme.shadow)

    painter.setPen(Qt.PenStyle.NoPen)
    fill = {
        SurfaceMode.NATIVE: theme.tint,
        SurfaceMode.TRANSLUCENT: theme.translucent_fill,
        SurfaceMode.OPAQUE: theme.opaque_fill,
    }[mode]
    painter.fillPath(shape, fill)

    painter.setClipPath(shape)
    _paint_specular(painter, body, theme.specular)
    painter.setClipping(False)
    _paint_stroke(painter, body, radius, theme)
    painter.restore()


def _paint_shadow(
    painter: QPainter, body: QRectF, radius: float, shape: QPainterPath, color: QColor
) -> None:
    layer = QColor(color)
    layer.setAlphaF(color.alphaF() / (_SHADOW_STEPS * 2.2))
    outside = QPainterPath()
    outside.addRect(body.adjusted(-SHADOW_MARGIN, -SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN))
    painter.save()
    painter.setClipPath(outside.subtracted(shape))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(layer)
    for step in range(_SHADOW_STEPS, 0, -1):
        grow = _SHADOW_SPREAD * step / _SHADOW_STEPS
        rect = body.translated(0, _SHADOW_OFFSET).adjusted(-grow, -grow, grow, grow)
        painter.drawRoundedRect(rect, radius + grow, radius + grow)
    painter.restore()


def _paint_specular(painter: QPainter, body: QRectF, color: QColor) -> None:
    glow = QLinearGradient(body.topLeft(), body.topLeft() + QPointF(0, _SPECULAR_DEPTH))
    faded = QColor(color)
    faded.setAlphaF(0.0)
    softened = QColor(color)
    softened.setAlphaF(color.alphaF() * 0.45)
    glow.setColorAt(0.0, softened)
    glow.setColorAt(1.0, faded)
    painter.fillRect(QRectF(body.left(), body.top(), body.width(), _SPECULAR_DEPTH), glow)

    edge_inset = min(body.height() / 2, 28.0)
    edge = QLinearGradient(
        QPointF(body.left() + edge_inset, 0), QPointF(body.right() - edge_inset, 0)
    )
    edge.setColorAt(0.0, faded)
    edge.setColorAt(0.5, color)
    edge.setColorAt(1.0, faded)
    painter.setPen(QPen(edge, 1.0))
    y = body.top() + 1.5
    painter.drawLine(QPointF(body.left() + edge_inset, y), QPointF(body.right() - edge_inset, y))


def _paint_stroke(painter: QPainter, body: QRectF, radius: float, theme: Theme) -> None:
    gradient = QLinearGradient(body.topLeft(), body.bottomRight())
    gradient.setColorAt(0.0, theme.stroke_start)
    gradient.setColorAt(1.0, theme.stroke_end)
    inset = body.adjusted(0.5, 0.5, -0.5, -0.5)
    painter.setPen(QPen(gradient, 1.0))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRoundedRect(inset, radius - 0.5, radius - 0.5)
