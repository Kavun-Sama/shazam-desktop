"""Status line with a shimmer sweep and the live input-level meter."""

from __future__ import annotations

import time
from collections import deque

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPaintEvent, QPen
from PySide6.QtWidgets import QGraphicsBlurEffect, QWidget

from shazam_desktop.ui.animation import Presence
from shazam_desktop.ui.theme import Theme, system_font

_CROSSFADE_MS = 220
_SWEEP_MS = 1800
_BLUR_RADIUS = 5.0
_BAND_WIDTH = 56.0


class ShimmerLabel(QWidget):
    """One line of text; changes cross-fade with a blur→sharp settle, and a highlight sweeps
    across it while the pipeline is busy."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._text = ""
        self._previous = ""
        self._mix = 1.0
        self._phase = 0.0
        self._shimmering = False
        self._muted = False
        self._reduce_motion = False
        self._font = system_font(QFont.Weight.Medium)
        self.setFont(self._font)

        self._presence = Presence(self, shown=True)
        self._presence.changed.connect(self.update)

        self._blur = QGraphicsBlurEffect(self)
        self._blur.setBlurHints(QGraphicsBlurEffect.BlurHint.QualityHint)
        self._blur.setEnabled(False)
        self.setGraphicsEffect(self._blur)

        self._fade = QVariantAnimation(self)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setDuration(_CROSSFADE_MS)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade.valueChanged.connect(self._on_fade)

        self._sweep = QVariantAnimation(self)
        self._sweep.setStartValue(0.0)
        self._sweep.setEndValue(1.0)
        self._sweep.setDuration(_SWEEP_MS)
        self._sweep.setEasingCurve(QEasingCurve.Type.Linear)
        self._sweep.setLoopCount(-1)
        self._sweep.valueChanged.connect(self._on_sweep)

    @property
    def text(self) -> str:
        return self._text

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_shown(self, shown: bool) -> None:
        self._presence.set_shown(shown)

    def set_reduce_motion(self, reduce: bool) -> None:
        self._reduce_motion = reduce
        self._sync_sweep()
        self.update()

    def set_muted(self, muted: bool) -> None:
        self._muted = muted
        self.update()

    def set_shimmering(self, shimmering: bool) -> None:
        self._shimmering = shimmering
        self._sync_sweep()
        self.update()

    def set_text(self, text: str, *, animate: bool = True) -> None:
        if text == self._text:
            return
        self._previous, self._text = self._text, text
        if animate and self._previous:
            self._fade.stop()
            self._mix = 0.0
            self._blur.setEnabled(not self._reduce_motion)
            self._blur.setBlurRadius(0.0 if self._reduce_motion else _BLUR_RADIUS)
            self._fade.start()
        else:
            self._finish_fade()
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(QFontMetrics(self._font).horizontalAdvance(self._text) + 2, 24)

    def paintEvent(self, event: QPaintEvent) -> None:
        presence = self._presence.value
        if presence <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        if self._previous and self._mix < 1.0:
            painter.setOpacity(presence * (1.0 - self._mix))
            self._draw(painter, self._previous)
        painter.setOpacity(presence * self._mix)
        self._draw(painter, self._text)

    def _draw(self, painter: QPainter, text: str) -> None:
        width = QFontMetrics(self._font).horizontalAdvance(text)
        if self._shimmering and not self._reduce_motion:
            painter.setPen(QPen(self._sweep_brush(width), 1.0))
        else:
            painter.setPen(self._theme.text_secondary if self._muted else self._theme.text)
        painter.drawText(
            QRectF(self.rect()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )

    def _sweep_brush(self, text_width: int) -> QLinearGradient:
        centre = -_BAND_WIDTH + (text_width + 2 * _BAND_WIDTH) * self._phase
        gradient = QLinearGradient(centre - _BAND_WIDTH / 2, 0, centre + _BAND_WIDTH / 2, 0)
        highlight = QColor(self._theme.text)
        highlight.setAlphaF(1.0)
        gradient.setColorAt(0.0, self._theme.text_secondary)
        gradient.setColorAt(0.5, highlight)
        gradient.setColorAt(1.0, self._theme.text_secondary)
        return gradient

    def _sync_sweep(self) -> None:
        running = self._shimmering and not self._reduce_motion
        if running and self._sweep.state() != QVariantAnimation.State.Running:
            self._sweep.start()
        elif not running:
            self._sweep.stop()

    def _on_sweep(self, value: object) -> None:
        # The last fifth of each cycle is a rest, so the sweep reads as a pulse, not a ticker.
        self._phase = min(1.0, float(value) * 1.25)  # type: ignore[arg-type]
        self.update()

    def _on_fade(self, value: object) -> None:
        self._mix = float(value)  # type: ignore[arg-type]
        if self._mix >= 1.0:
            self._finish_fade()
        elif not self._reduce_motion:
            self._blur.setBlurRadius(_BLUR_RADIUS * (1.0 - self._mix))
        self.update()

    def _finish_fade(self) -> None:
        self._mix = 1.0
        self._previous = ""
        self._blur.setEnabled(False)


class LevelMeter(QWidget):
    """Four bars driven by the most recent input levels."""

    BARS = 4
    _BAR_WIDTH = 3
    _GAP = 3
    _MIN_HEIGHT = 4.0
    _MAX_HEIGHT = 18.0
    _STALE_AFTER = 0.15

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._history: deque[float] = deque([0.0] * self.BARS, maxlen=self.BARS)
        self._shown = [0.0] * self.BARS
        self._last_push = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self._presence = Presence(self, shown=False)
        self._presence.changed.connect(self._on_presence)
        self.setFixedSize(
            self.BARS * self._BAR_WIDTH + (self.BARS - 1) * self._GAP, int(self._MAX_HEIGHT) + 2
        )

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def push(self, level: float) -> None:
        self._history.append(max(0.0, min(1.0, level)))
        self._last_push = time.monotonic()

    def set_shown(self, shown: bool) -> None:
        """Fade the meter in while capturing and out afterwards; it only ticks while visible."""
        if shown:
            self._timer.start()
        self._presence.set_shown(shown)

    def _on_presence(self) -> None:
        if self._presence.value <= 0.0 and not self._presence.target:
            self._timer.stop()
            self._history.extend([0.0] * self.BARS)
            self._shown = [0.0] * self.BARS
        self.update()

    def _tick(self) -> None:
        stale = time.monotonic() - self._last_push > self._STALE_AFTER
        for index, target in enumerate(self._history):
            goal = 0.0 if stale else target
            self._shown[index] += (goal - self._shown[index]) * 0.35
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._presence.value <= 0.0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self._presence.value)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(self._theme.text)
        for index, level in enumerate(self._shown):
            height = self._MIN_HEIGHT + (self._MAX_HEIGHT - self._MIN_HEIGHT) * level
            x = index * (self._BAR_WIDTH + self._GAP)
            y = (self.height() - height) / 2
            painter.drawRoundedRect(
                QRectF(x, y, self._BAR_WIDTH, height), self._BAR_WIDTH / 2, self._BAR_WIDTH / 2
            )
