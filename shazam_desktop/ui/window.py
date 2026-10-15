"""The single frameless Liquid Glass window."""

from __future__ import annotations

from collections.abc import Callable
from enum import Enum, auto
from typing import Protocol

from PySide6.QtCore import QEasingCurve, QPoint, QRect, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import (
    QCloseEvent,
    QColor,
    QFont,
    QGuiApplication,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QMoveEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QShortcut,
    QShowEvent,
)
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from shazam_desktop.controller import Controller
from shazam_desktop.errors import ErrorKind
from shazam_desktop.recognition.models import Track
from shazam_desktop.state import Phase, State
from shazam_desktop.ui.accessibility import SystemPreferences, read_system_preferences
from shazam_desktop.ui.animation import Fader, clamp, lerp
from shazam_desktop.ui.buttons import RoundButton, SourceButton, TextButton
from shazam_desktop.ui.cover_loader import CoverLoader
from shazam_desktop.ui.glass import NativeBackdrop, create_backdrop
from shazam_desktop.ui.icons import Icon
from shazam_desktop.ui.messages import ERROR_COPY, IDLE_HINT, PHASE_TEXT
from shazam_desktop.ui.result import CopyField, CoverView, GlyphView
from shazam_desktop.ui.source_menu import SourceMenu
from shazam_desktop.ui.status import LevelMeter, ShimmerLabel
from shazam_desktop.ui.surface import SHADOW_MARGIN, SurfaceMode, paint_surface
from shazam_desktop.ui.theme import Theme, build_theme, system_font

BODY_WIDTH = 320
PILL_HEIGHT = 72
CARD_HEIGHT = 128
PAD = 16
FOOTER_HEIGHT = 32
FOOTER_INSET = 8
MAIN_SIZE_PILL = 40
MAIN_SIZE_CARD = 32
PILL_RADIUS = 36.0
CARD_RADIUS = 28.0
EXPAND_MS = 250
OVERSHOOT = 1.0

_STATUS_X = PAD + MAIN_SIZE_PILL + 12
_TEXT_X = PAD + 64 + 12


class View(Enum):
    IDLE = auto()
    BUSY = auto()
    RESULT = auto()
    ERROR = auto()


class _Themed(Protocol):
    def set_theme(self, theme: Theme) -> None: ...


class MainWindow(QWidget):
    """Pill at rest; expands into a result or error card. Owns no business logic."""

    def __init__(
        self,
        controller: Controller,
        *,
        preferences: Callable[[], SystemPreferences] = read_system_preferences,
    ) -> None:
        super().__init__(
            None,
            Qt.WindowType.Window
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.NoDropShadowWindowHint,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setWindowTitle("Shazam Desktop")

        self._controller = controller
        self._read_preferences = preferences
        self._prefs = preferences()
        self._theme = build_theme(self._system_is_dark(), self._system_accent())
        self._backdrop: NativeBackdrop | None = None
        self._backdrop_tried = False
        self._native_active = False
        self._surface_ready = False
        self._margin = SHADOW_MARGIN
        self._height = float(PILL_HEIGHT)
        self._view = View.IDLE
        self._anchor = QPoint(0, 0)
        self._placed = False
        self._applying = False

        self._body = QWidget(self)
        self._themed: list[_Themed] = []
        self._build_status()
        self._build_result()
        self._build_error()
        self._build_controls()
        self._build_faders()
        self._build_behaviour()
        self._apply_theme()
        self._apply_preferences_to_children()
        self._refresh_source()
        self._apply_geometry()

    # ------------------------------------------------------------------ construction

    def _track(self, widget: _Themed) -> None:
        self._themed.append(widget)

    def _build_status(self) -> None:
        self._status_group = QWidget(self._body)
        self._status = ShimmerLabel(self._theme, self._status_group)
        self._status.set_text(IDLE_HINT, animate=False)
        self._status.set_muted(True)
        self._meter = LevelMeter(self._theme, self._status_group)
        self._track(self._status)
        self._track(self._meter)

        width = BODY_WIDTH - _STATUS_X - PAD
        self._status_group.setGeometry(_STATUS_X, 0, width, PILL_HEIGHT)
        meter_x = width - self._meter.width()
        self._status.setGeometry(0, (PILL_HEIGHT - 24) // 2, meter_x - 8, 24)
        self._meter.move(meter_x, (PILL_HEIGHT - self._meter.height()) // 2)

    def _build_result(self) -> None:
        self._result_layer = QWidget(self._body)
        self._result_layer.setGeometry(0, 0, BODY_WIDTH, CARD_HEIGHT)
        self._cover = CoverView(self._theme, self._result_layer)
        self._cover.move(PAD, PAD)
        self._title = CopyField(self._theme, emphasized=True, parent=self._result_layer)
        self._artist = CopyField(self._theme, emphasized=False, parent=self._result_layer)
        text_width = BODY_WIDTH - _TEXT_X - PAD
        self._title.setGeometry(_TEXT_X, 24, text_width, CopyField.HEIGHT)
        self._artist.setGeometry(_TEXT_X, 48, text_width, CopyField.HEIGHT)
        for widget in (self._cover, self._title, self._artist):
            self._track(widget)
        self._loader = CoverLoader(self)
        self._loader.loaded.connect(self._cover.set_pixmap)

    def _build_error(self) -> None:
        self._error_layer = QWidget(self._body)
        self._error_layer.setGeometry(0, 0, BODY_WIDTH, CARD_HEIGHT)
        self._error_icon = GlyphView(Icon.WARNING, 24, self._error_layer)
        self._error_icon.move(PAD, PAD)
        text_x = PAD + 24 + 12
        text_width = BODY_WIDTH - text_x - PAD
        self._error_title = QLabel(self._error_layer)
        self._error_title.setFont(system_font(QFont.Weight.DemiBold))
        self._error_title.setGeometry(text_x, PAD, text_width, 24)
        self._error_hint = QLabel(self._error_layer)
        self._error_hint.setFont(system_font())
        self._error_hint.setWordWrap(True)
        self._error_hint.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self._error_hint.setGeometry(text_x, PAD + 26, text_width, 40)

    def _build_controls(self) -> None:
        self._main = RoundButton(self._theme, self._body)
        self._source = SourceButton(self._theme, self._body)
        self._retry = TextButton("Try again", self._theme, self._body)
        for widget in (self._main, self._source, self._retry):
            self._track(widget)
        self._menu = SourceMenu(self._controller, self)

    def _build_faders(self) -> None:
        self._result_fader = Fader(self._result_layer, visible=False)
        self._error_fader = Fader(self._error_layer, visible=False)
        self._main_fader = Fader(self._main, visible=True)
        self._source_fader = Fader(self._source, visible=True)
        self._retry_fader = Fader(self._retry, visible=False)

    def _build_behaviour(self) -> None:
        self._height_animation = QVariantAnimation(self)
        self._height_animation.setDuration(EXPAND_MS)
        self._height_animation.valueChanged.connect(self._on_height)

        self._main.clicked.connect(self._controller.toggle)
        self._retry.clicked.connect(self._controller.start)
        self._source.clicked.connect(self._open_source_menu)
        self._controller.state_changed.connect(self.apply_state)
        self._controller.level_changed.connect(self.push_level)
        self._controller.source_changed.connect(self._refresh_source)
        QGuiApplication.styleHints().colorSchemeChanged.connect(self._on_scheme_changed)

        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(QApplication.quit)

    # ------------------------------------------------------------------ public API

    def present(self) -> None:
        """Show the window above everything else and focus it."""
        self._refresh_preferences()
        if not self._placed:
            self._place_initially()
        self.show()
        self.raise_()
        self.activateWindow()

    def apply_state(self, state: State) -> None:
        """Reflect a controller state: swap layers, resize and update the status line."""
        if state.phase is Phase.IDLE:
            view = View.IDLE
        elif state.active:
            view = View.BUSY
        elif state.phase is Phase.RESULT:
            view = View.RESULT
        else:
            view = View.ERROR

        if view in (View.IDLE, View.BUSY):
            self._update_status(state)
        if view is View.RESULT and state.track is not None:
            self._show_track(state.track)
        if view is View.ERROR and state.error is not None:
            self._show_error(state.error)

        busy = view is View.BUSY
        self._main.set_glyph(Icon.STOP if busy else Icon.MIC, active=busy)
        self._status.set_shown(view in (View.IDLE, View.BUSY))
        self._meter.set_shown(busy)
        self._result_fader.set_visible(view is View.RESULT)
        self._error_fader.set_visible(view is View.ERROR)
        self._main_fader.set_visible(view is not View.ERROR)
        self._retry_fader.set_visible(view is View.ERROR)
        self._source_fader.set_visible(view is not View.BUSY)

        self._view = view
        self._animate_height(float(PILL_HEIGHT if view in (View.IDLE, View.BUSY) else CARD_HEIGHT))

    def push_level(self, level: float) -> None:
        self._meter.push(level)

    def set_dark(self, dark: bool) -> None:
        self._theme = build_theme(dark, self._system_accent())
        self._apply_theme()

    # ------------------------------------------------------------------ state → widgets

    def _update_status(self, state: State) -> None:
        if state.active:
            self._status.set_muted(False)
            self._status.set_shimmering(True)
            self._status.set_text(PHASE_TEXT[state.phase])
        else:
            self._status.set_shimmering(False)
            self._status.set_muted(True)
            self._status.set_text(IDLE_HINT)

    def _show_track(self, track: Track) -> None:
        self._title.set_text(track.title, "Unknown title")
        self._artist.set_text(track.artist, "Unknown artist")
        self._cover.clear()
        self._loader.cancel()
        if track.cover_url:
            self._loader.load(track.cover_url)

    def _show_error(self, kind: ErrorKind) -> None:
        title, hint = ERROR_COPY[kind]
        self._error_title.setText(title)
        self._error_hint.setText(hint)

    # ------------------------------------------------------------------ geometry

    def _animate_height(self, target: float) -> None:
        self._height_animation.stop()
        if target == self._height:
            return
        if self._prefs.reduce_motion or not self.isVisible():
            self._set_height(target)
            return
        expanding = target > self._height
        curve = QEasingCurve(QEasingCurve.Type.OutBack if expanding else QEasingCurve.Type.OutCubic)
        if expanding:
            curve.setOvershoot(OVERSHOOT)
        self._height_animation.setEasingCurve(curve)
        self._height_animation.setStartValue(self._height)
        self._height_animation.setEndValue(target)
        self._height_animation.start()

    def _on_height(self, value: object) -> None:
        self._set_height(float(value))  # type: ignore[arg-type]

    def _set_height(self, height: float) -> None:
        self._height = height
        self._apply_geometry()

    def _expansion(self) -> float:
        return clamp((self._height - PILL_HEIGHT) / (CARD_HEIGHT - PILL_HEIGHT))

    def _radius(self) -> float:
        return lerp(PILL_RADIUS, CARD_RADIUS, self._expansion())

    def _available_geometry(self) -> QRect:
        screen = self.screen() or QGuiApplication.primaryScreen()
        return screen.availableGeometry()

    def _apply_geometry(self) -> None:
        margin = self._margin
        height = round(self._height)
        outer_height = height + 2 * margin
        left = self._anchor.x() - margin
        top = min(self._anchor.y() - margin, self._available_geometry().bottom() - outer_height + 1)
        self._applying = True
        self.setGeometry(left, top, BODY_WIDTH + 2 * margin, outer_height)
        self._applying = False
        self._body.setGeometry(margin, margin, BODY_WIDTH, height)
        self._layout_controls()
        if self._backdrop is not None:
            self._backdrop.update_shape(BODY_WIDTH, height, self._radius())
        self.update()

    def _layout_controls(self) -> None:
        height = self._height
        amount = self._expansion()

        size = round(lerp(MAIN_SIZE_PILL, MAIN_SIZE_CARD, amount))
        centre_y = lerp(PILL_HEIGHT / 2, height - FOOTER_INSET - FOOTER_HEIGHT / 2, amount)
        self._main.setGeometry(PAD, round(centre_y - size / 2), size, size)

        source_width = self._source.sizeHint().width()
        source_y = lerp(
            (PILL_HEIGHT - FOOTER_HEIGHT) / 2, height - FOOTER_INSET - FOOTER_HEIGHT, amount
        )
        self._source.setGeometry(
            BODY_WIDTH - PAD - source_width, round(source_y), source_width, FOOTER_HEIGHT
        )

        retry_width = self._retry.sizeHint().width()
        self._retry.setGeometry(
            PAD, round(height - FOOTER_INSET - FOOTER_HEIGHT), retry_width, FOOTER_HEIGHT
        )

    def _place_initially(self) -> None:
        available = self._available_geometry()
        self._anchor = QPoint(
            available.center().x() - BODY_WIDTH // 2,
            available.top() + round(available.height() * 0.18),
        )
        self._placed = True
        self._apply_geometry()

    # ------------------------------------------------------------------ surface and theme

    def _surface_mode(self) -> SurfaceMode:
        if self._prefs.reduce_transparency:
            return SurfaceMode.OPAQUE
        return SurfaceMode.NATIVE if self._native_active else SurfaceMode.TRANSLUCENT

    def _refresh_preferences(self) -> None:
        self._prefs = self._read_preferences()
        self._apply_preferences_to_children()
        self._apply_surface()

    def _apply_preferences_to_children(self) -> None:
        self._status.set_reduce_motion(self._prefs.reduce_motion)

    def _apply_surface(self) -> None:
        want_native = not self._prefs.reduce_transparency
        if want_native and not self._backdrop_tried:
            self._backdrop_tried = True
            self._backdrop = create_backdrop(self)
        self._native_active = False
        if self._backdrop is not None:
            self._backdrop.set_dark(self._theme.dark)
            self._native_active = self._backdrop.set_enabled(want_native)
        self._margin = 0 if self._native_active else SHADOW_MARGIN
        self._surface_ready = True
        self._apply_geometry()

    def _apply_theme(self) -> None:
        for widget in self._themed:
            widget.set_theme(self._theme)
        self._error_icon.set_color(self._theme.warning)
        for label, color in (
            (self._error_title, self._theme.text),
            (self._error_hint, self._theme.text_secondary),
        ):
            self._paint_label(label, color)
        if self._backdrop is not None:
            self._backdrop.set_dark(self._theme.dark)
        self.update()

    @staticmethod
    def _paint_label(label: QLabel, color: QColor) -> None:
        palette = label.palette()
        palette.setColor(QPalette.ColorRole.WindowText, color)
        label.setPalette(palette)

    @staticmethod
    def _system_is_dark() -> bool:
        return QGuiApplication.styleHints().colorScheme() == Qt.ColorScheme.Dark

    @staticmethod
    def _system_accent() -> QColor:
        return QGuiApplication.palette().color(QPalette.ColorRole.Accent)

    def _on_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        self.set_dark(self._system_is_dark())

    # ------------------------------------------------------------------ source menu

    def _refresh_source(self, _key: str = "") -> None:
        self._source.set_label(self._controller.source_label())
        self._layout_controls()

    def _open_source_menu(self) -> None:
        self._menu.refresh()
        size = self._menu.sizeHint()
        corner = self._source.mapToGlobal(QPoint(self._source.width(), self._source.height() + 4))
        self._menu.popup(QPoint(corner.x() - size.width(), corner.y()))

    # ------------------------------------------------------------------ Qt events

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        body = QRectF(self._margin, self._margin, BODY_WIDTH, self._height)
        paint_surface(painter, body, self._radius(), self._theme, self._surface_mode())

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._surface_ready:
            self._refresh_preferences()

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        if not self._applying and self.isVisible():
            self._anchor = self.pos() + QPoint(self._margin, self._margin)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        handle = self.windowHandle()
        if event.button() == Qt.MouseButton.LeftButton and handle is not None:
            handle.startSystemMove()
            event.accept()
            return
        super().mousePressEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if self._controller.state.active:
                self._controller.cancel()
            else:
                self.hide()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()
