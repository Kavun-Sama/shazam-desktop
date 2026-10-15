"""Vector icons drawn with QPainter so they follow text color and any scale."""

from __future__ import annotations

from enum import Enum, auto

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

_GRID = 24.0


class Icon(Enum):
    MIC = auto()
    STOP = auto()
    COPY = auto()
    CHECK = auto()
    CHEVRON_DOWN = auto()
    WARNING = auto()


def paint_icon(painter: QPainter, icon: Icon, rect: QRectF, color: QColor) -> None:
    """Draw ``icon`` into ``rect`` using ``color`` for strokes and fills."""
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.translate(rect.topLeft())
    painter.scale(rect.width() / _GRID, rect.height() / _GRID)
    pen = QPen(color, 2.0)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    _DRAWERS[icon](painter, color)
    painter.restore()


def _mic(painter: QPainter, color: QColor) -> None:
    painter.drawRoundedRect(QRectF(9, 2.5, 6, 11.5), 3, 3)
    arc = QPainterPath()
    arc.moveTo(5.5, 11.5)
    arc.arcTo(QRectF(5.5, 5, 13, 13), 180, 180)
    painter.drawPath(arc)
    painter.drawLine(QPointF(12, 18), QPointF(12, 21.5))
    painter.drawLine(QPointF(8.5, 21.5), QPointF(15.5, 21.5))


def _stop(painter: QPainter, color: QColor) -> None:
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 2.5, 2.5)


def _copy(painter: QPainter, color: QColor) -> None:
    front = QRectF(4, 8.5, 11.5, 11.5)
    back = QRectF(8.5, 4, 11.5, 11.5)
    keep_out = QPainterPath()
    keep_out.addRoundedRect(front.adjusted(-1.5, -1.5, 1.5, 1.5), 3.5, 3.5)
    visible = QPainterPath()
    visible.addRect(QRectF(0, 0, _GRID, _GRID))
    painter.save()
    painter.setClipPath(visible.subtracted(keep_out))
    painter.drawRoundedRect(back, 2.5, 2.5)
    painter.restore()
    painter.drawRoundedRect(front, 2.5, 2.5)


def _check(painter: QPainter, color: QColor) -> None:
    path = QPainterPath()
    path.moveTo(5, 12.5)
    path.lineTo(10, 17.5)
    path.lineTo(19, 7)
    painter.drawPath(path)


def _chevron_down(painter: QPainter, color: QColor) -> None:
    path = QPainterPath()
    path.moveTo(6.5, 9.5)
    path.lineTo(12, 15)
    path.lineTo(17.5, 9.5)
    painter.drawPath(path)


def _warning(painter: QPainter, color: QColor) -> None:
    painter.drawEllipse(QRectF(3, 3, 18, 18))
    painter.drawLine(QPointF(12, 7.5), QPointF(12, 13))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(color)
    painter.drawEllipse(QPointF(12, 16.6), 1.15, 1.15)


_DRAWERS = {
    Icon.MIC: _mic,
    Icon.STOP: _stop,
    Icon.COPY: _copy,
    Icon.CHECK: _check,
    Icon.CHEVRON_DOWN: _chevron_down,
    Icon.WARNING: _warning,
}


def tray_icon(color: QColor, mask: bool = False) -> QIcon:
    """Menu-bar / tray glyph; ``mask`` lets macOS recolor it for the menu bar."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    paint_icon(painter, Icon.MIC, QRectF(8, 8, 48, 48), color)
    painter.end()
    icon = QIcon(pixmap)
    icon.setIsMask(mask)
    return icon
