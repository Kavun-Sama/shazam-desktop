"""Glass-friendly controls: no opaque fills, only hairlines and translucent hover states."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QFont, QFontMetrics, QPainter, QPaintEvent
from PySide6.QtWidgets import QAbstractButton, QWidget

from shazam_desktop.ui.icons import Icon, paint_icon
from shazam_desktop.ui.theme import Theme, system_font


class RoundButton(QAbstractButton):
    """Circular primary control; its ring and glyph switch to the accent color while active."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._icon = Icon.MIC
        self._active = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_glyph(self, icon: Icon, *, active: bool) -> None:
        self._icon = icon
        self._active = active
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        ring = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        accent = self._theme.accent if self._active else self._theme.text

        if self.isDown():
            painter.setBrush(self._theme.pressed)
        elif self.underMouse():
            painter.setBrush(self._theme.hover)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(self._theme.accent if self._active else self._theme.text_secondary)
        pen = painter.pen()
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawEllipse(ring)

        side = ring.width() * 0.5
        glyph = QRectF(0, 0, side, side)
        glyph.moveCenter(ring.center())
        paint_icon(painter, self._icon, glyph, accent)


class TextButton(QAbstractButton):
    """Capsule action with an accent hairline, e.g. "Try again"."""

    HEIGHT = 32

    def __init__(self, text: str, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self.setText(text)
        self.setFont(system_font(QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(QFontMetrics(self.font()).horizontalAdvance(self.text()) + 32, self.HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.75, 0.75, -0.75, -0.75)
        accent = self._theme.accent
        if self.isDown() or self.underMouse():
            fill = accent.toRgb()
            fill.setAlphaF(0.22 if self.isDown() else 0.12)
            painter.setBrush(fill)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(accent)
        pen = painter.pen()
        pen.setWidthF(1.5)
        painter.setPen(pen)
        painter.drawRoundedRect(rect, rect.height() / 2, rect.height() / 2)
        painter.setFont(self.font())
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class SourceButton(QAbstractButton):
    """Source selector: current label plus a chevron; opens a menu."""

    HEIGHT = 32
    MAX_LABEL_WIDTH = 88
    _PAD = 12
    _CHEVRON = 12
    _GAP = 4

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._label = ""
        self.setFont(system_font(QFont.Weight.Medium))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_label(self, label: str) -> None:
        self._label = label
        self.setToolTip(label)
        self.updateGeometry()
        self.update()

    def _elided(self) -> str:
        metrics = QFontMetrics(self.font())
        return metrics.elidedText(self._label, Qt.TextElideMode.ElideRight, self.MAX_LABEL_WIDTH)

    def sizeHint(self) -> QSize:
        text_width = QFontMetrics(self.font()).horizontalAdvance(self._elided())
        width = self._PAD + text_width + self._GAP + self._CHEVRON + self._PAD - 4
        return QSize(width, self.HEIGHT)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.isDown():
            painter.setBrush(self._theme.pressed)
        elif self.underMouse():
            painter.setBrush(self._theme.hover)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(self.rect(), self.height() / 2, self.height() / 2)

        color = self._theme.text if self.underMouse() else self._theme.text_secondary
        painter.setPen(color)
        painter.setFont(self.font())
        text_rect = QRectF(
            self._PAD, 0, self.width() - self._PAD - self._CHEVRON - 8, self.height()
        )
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._elided(),
        )
        chevron = QRectF(0, 0, self._CHEVRON, self._CHEVRON)
        chevron.moveCenter(
            QRectF(
                self.width() - self._PAD - self._CHEVRON / 2 + 2, self.height() / 2, 0, 0
            ).topLeft()
        )
        paint_icon(painter, Icon.CHEVRON_DOWN, chevron, color)
