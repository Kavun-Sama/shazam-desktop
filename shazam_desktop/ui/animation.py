"""Small animation helpers shared by the window and its widgets."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QObject, QVariantAnimation, Signal
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

FADE_IN_MS = 180
FADE_OUT_MS = 140


def lerp(start: float, end: float, amount: float) -> float:
    return start + (end - start) * amount


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


class Fader(QObject):
    """Cross-fades a widget and hides it once invisible, so it stops receiving input."""

    def __init__(self, widget: QWidget, *, visible: bool) -> None:
        super().__init__(widget)
        self._widget = widget
        self._target = visible
        self._effect = QGraphicsOpacityEffect(widget)
        self._effect.setOpacity(1.0 if visible else 0.0)
        widget.setGraphicsEffect(self._effect)
        widget.setVisible(visible)

        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._apply)
        self._animation.finished.connect(self._settle)

    @property
    def target(self) -> bool:
        return self._target

    def set_visible(self, visible: bool, *, animated: bool = True) -> None:
        if visible == self._target:
            return
        self._target = visible
        self._animation.stop()
        start = self._effect.opacity()
        end = 1.0 if visible else 0.0
        if visible:
            self._widget.show()
        duration = round(abs(end - start) * (FADE_IN_MS if visible else FADE_OUT_MS))
        if not animated or duration == 0:
            self._apply(end)
            self._settle()
            return
        self._animation.setStartValue(start)
        self._animation.setEndValue(end)
        self._animation.setDuration(duration)
        self._animation.start()

    def _apply(self, value: object) -> None:
        self._effect.setOpacity(float(value))  # type: ignore[arg-type]

    def _settle(self) -> None:
        if not self._target:
            self._widget.hide()


class Presence(QObject):
    """Animated 0..1 visibility for widgets that fade themselves while painting.

    Used instead of :class:`Fader` where the widget already owns a graphics effect,
    because Qt does not render nested effects reliably.
    """

    changed = Signal()

    def __init__(self, parent: QObject, *, shown: bool) -> None:
        super().__init__(parent)
        self._value = 1.0 if shown else 0.0
        self._target = shown
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_value)

    @property
    def value(self) -> float:
        return self._value

    @property
    def target(self) -> bool:
        return self._target

    def set_shown(self, shown: bool, *, animated: bool = True) -> None:
        if shown == self._target:
            return
        self._target = shown
        self._animation.stop()
        end = 1.0 if shown else 0.0
        duration = round(abs(end - self._value) * (FADE_IN_MS if shown else FADE_OUT_MS))
        if not animated or duration == 0:
            self._on_value(end)
            return
        self._animation.setStartValue(self._value)
        self._animation.setEndValue(end)
        self._animation.setDuration(duration)
        self._animation.start()

    def _on_value(self, value: object) -> None:
        self._value = float(value)  # type: ignore[arg-type]
        self.changed.emit()
