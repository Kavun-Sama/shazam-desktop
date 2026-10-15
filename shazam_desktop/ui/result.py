"""Result card parts: cover art, copyable text fields and the error glyph."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, QSize, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QGuiApplication,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPixmap,
    QResizeEvent,
)
from PySide6.QtWidgets import QAbstractButton, QWidget

from shazam_desktop.ui.icons import Icon, paint_icon
from shazam_desktop.ui.theme import Theme, system_font

COVER_SIZE = 64
COVER_RADIUS = 12.0
_REVEAL_MS = 260
_COPIED_MS = 1200


class CoverView(QWidget):
    """Rounded cover art; shows a placeholder until the image arrives, then fades it in."""

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._pixmap: QPixmap | None = None
        self._reveal = 0.0
        self.setFixedSize(COVER_SIZE, COVER_SIZE)
        self._animation = QVariantAnimation(self)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(1.0)
        self._animation.setDuration(_REVEAL_MS)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._on_reveal)

    @property
    def has_image(self) -> bool:
        return self._pixmap is not None

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def clear(self) -> None:
        self._animation.stop()
        self._pixmap = None
        self._reveal = 0.0
        self.update()

    def set_pixmap(self, pixmap: QPixmap) -> None:
        ratio = self.devicePixelRatioF()
        side = round(COVER_SIZE * ratio)
        scaled = pixmap.scaled(
            side,
            side,
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            Qt.TransformationMode.SmoothTransformation,
        )
        # Centre-crop to a square when the source is not one.
        x = (scaled.width() - side) // 2
        y = (scaled.height() - side) // 2
        self._pixmap = scaled.copy(x, y, side, side)
        self._pixmap.setDevicePixelRatio(ratio)
        self._animation.stop()
        self._animation.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        rect = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(rect, COVER_RADIUS, COVER_RADIUS)

        placeholder = self._theme.hairline
        painter.fillPath(clip, placeholder)
        if self._pixmap is not None:
            painter.save()
            painter.setClipPath(clip)
            painter.setOpacity(self._reveal)
            painter.drawPixmap(0, 0, self._pixmap)
            painter.restore()

        outline = rect.adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(self._theme.hairline)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(outline, COVER_RADIUS - 0.5, COVER_RADIUS - 0.5)

    def _on_reveal(self, value: object) -> None:
        self._reveal = float(value)  # type: ignore[arg-type]
        self.update()


class _CopyButton(QAbstractButton):
    SIZE = 24

    def __init__(self, theme: Theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._copied = False
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setToolTip("Copy")

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.update()

    def set_copied(self, copied: bool) -> None:
        self._copied = copied
        self.update()

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
        painter.drawRoundedRect(QRectF(self.rect()), 7, 7)
        glyph = QRectF(0, 0, 14, 14)
        glyph.moveCenter(QRectF(self.rect()).center())
        if self._copied:
            paint_icon(painter, Icon.CHECK, glyph, self._theme.success)
        else:
            paint_icon(painter, Icon.COPY, glyph, self._theme.text_secondary)


class CopyField(QWidget):
    """One line of text with a copy button; clicking the text copies it as well."""

    HEIGHT = 24
    _GAP = 2

    def __init__(self, theme: Theme, *, emphasized: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._emphasized = emphasized
        self._font = system_font(QFont.Weight.DemiBold if emphasized else QFont.Weight.Normal)
        self._text: str | None = None
        self._placeholder = ""
        self._shown = ""
        self._text_width = 0
        self.setFont(self._font)
        self.setMouseTracking(True)

        self._button = _CopyButton(theme, self)
        self._button.clicked.connect(self.copy)
        self._reset = QTimer(self)
        self._reset.setSingleShot(True)
        self._reset.setInterval(_COPIED_MS)
        self._reset.timeout.connect(self._clear_copied)

    @property
    def text(self) -> str | None:
        return self._text

    @property
    def copied(self) -> bool:
        return self._reset.isActive()

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self._button.set_theme(theme)
        self.update()

    def set_text(self, text: str | None, placeholder: str) -> None:
        self._text = text
        self._placeholder = placeholder
        self._clear_copied()
        self._relayout()

    def copy(self) -> None:
        if self._text is None:
            return
        QGuiApplication.clipboard().setText(self._text)
        self._button.set_copied(True)
        self._reset.start()

    def sizeHint(self) -> QSize:
        return QSize(200, self.HEIGHT)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._relayout()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setFont(self._font)
        if self._text is None:
            painter.setPen(self._theme.text_secondary)
        else:
            painter.setPen(self._theme.text if self._emphasized else self._theme.text_secondary)
        painter.drawText(
            QRectF(0, 0, self._text_width + 1, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self._shown,
        )

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        over_text = self._text is not None and event.position().x() <= self._text_width
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if over_text else Qt.CursorShape.ArrowCursor
        )

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and event.position().x() <= self._text_width:
            self.copy()

    def _relayout(self) -> None:
        metrics = QFontMetrics(self._font)
        source = self._text if self._text is not None else self._placeholder
        available = self.width() - (_CopyButton.SIZE + self._GAP if self._text else 0)
        self._shown = metrics.elidedText(source, Qt.TextElideMode.ElideRight, max(available, 0))
        self._text_width = metrics.horizontalAdvance(self._shown)
        self.setToolTip(self._text if self._text and self._shown != self._text else "")
        self._button.setVisible(self._text is not None)
        self._button.move(self._text_width + self._GAP, (self.height() - _CopyButton.SIZE) // 2)
        self.update()

    def _clear_copied(self) -> None:
        self._reset.stop()
        self._button.set_copied(False)


class GlyphView(QWidget):
    """A static icon, used for the error glyph."""

    def __init__(self, icon: Icon, size: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._icon = icon
        self._color: QColor | None = None
        self.setFixedSize(size, size)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        if self._color is None:
            return
        painter = QPainter(self)
        paint_icon(painter, self._icon, QRectF(self.rect()), self._color)
