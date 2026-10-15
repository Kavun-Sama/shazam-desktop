"""Render every window state offscreen and save screenshots.

Usage: ``python scripts/capture_screenshots.py [output_dir]``.

The offscreen platform has no compositor, so the native backdrop blur is not
exercised here; the glass is composited over a synthetic wallpaper to make the
tint, stroke and specular layers visible.
"""

from __future__ import annotations

import itertools
import os
import sys
import tempfile
from collections.abc import Callable
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_SCALE_FACTOR", "2")

from PySide6.QtCore import QEventLoop, QPointF, QRectF, Qt, QTimer, QUrl
from PySide6.QtGui import (
    QColor,
    QFont,
    QImage,
    QLinearGradient,
    QPainter,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication

from shazam_desktop.audio.backend import AudioStream, FrameCallback
from shazam_desktop.audio.sources import (
    AudioSource,
    InputDevice,
    SourceCatalog,
    build_catalog,
)
from shazam_desktop.controller import Controller
from shazam_desktop.errors import ErrorKind
from shazam_desktop.recognition.models import Track
from shazam_desktop.settings.config import SettingsStore
from shazam_desktop.state import Phase, State
from shazam_desktop.ui.accessibility import SystemPreferences
from shazam_desktop.ui.result import CopyField
from shazam_desktop.ui.source_menu import SourceMenu
from shazam_desktop.ui.window import MainWindow

LEVELS = (0.25, 0.55, 0.85, 0.6, 0.35, 0.7)


class StubBackend:
    def list_sources(self) -> SourceCatalog:
        return build_catalog(
            [InputDevice(1, "MacBook Pro Microphone"), InputDevice(2, "USB Audio Device")],
            default_index=1,
            loopback=None,
            system_hint="Install BlackHole. See the README.",
        )

    def open_stream(self, source: AudioSource, on_frames: FrameCallback) -> AudioStream:
        raise NotImplementedError


class StubRecognizer:
    def recognize(self, wav: bytes, *, on_matching: Callable[[], None]) -> Track | None:
        raise NotImplementedError


def settle(milliseconds: int, tick: Callable[[], None] | None = None) -> None:
    loop = QEventLoop()
    timer = QTimer()
    if tick is not None:
        timer.timeout.connect(tick)
        timer.start(30)
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()
    timer.stop()


def level_feed(window: MainWindow) -> Callable[[], None]:
    """Return a callback that feeds the meter a repeating level pattern."""
    levels = itertools.cycle(LEVELS)
    return lambda: window.push_level(next(levels))


def make_cover(path: Path) -> str:
    image = QImage(400, 400, QImage.Format.Format_RGB32)
    painter = QPainter(image)
    gradient = QLinearGradient(0, 0, 400, 400)
    gradient.setColorAt(0.0, QColor("#ff6a5c"))
    gradient.setColorAt(1.0, QColor("#4a3cff"))
    painter.fillRect(image.rect(), gradient)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(255, 255, 255, 70))
    painter.drawEllipse(QPointF(150, 250), 140, 140)
    painter.setBrush(QColor(0, 0, 0, 60))
    painter.drawEllipse(QPointF(280, 130), 90, 90)
    painter.end()
    image.save(str(path))
    return QUrl.fromLocalFile(str(path)).toString()


def wallpaper(width: int, height: int, dark: bool) -> QImage:
    image = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
    painter = QPainter(image)
    base = QLinearGradient(0, 0, width, height)
    if dark:
        base.setColorAt(0.0, QColor("#16213e"))
        base.setColorAt(1.0, QColor("#3a1c4e"))
    else:
        base.setColorAt(0.0, QColor("#9ad0ff"))
        base.setColorAt(1.0, QColor("#ffc9a8"))
    painter.fillRect(image.rect(), base)
    for x, y, radius, color in (
        (0.2, 0.3, 0.45, "#ff4d8d"),
        (0.8, 0.7, 0.5, "#ffd23f"),
        (0.55, 0.2, 0.35, "#2ec4b6"),
    ):
        glow = QRadialGradient(QPointF(width * x, height * y), width * radius)
        tone = QColor(color)
        tone.setAlpha(150 if not dark else 110)
        glow.setColorAt(0.0, tone)
        tone.setAlpha(0)
        glow.setColorAt(1.0, tone)
        painter.fillRect(image.rect(), glow)
    painter.end()
    return image


def composite(window: MainWindow, dark: bool) -> QImage:
    pixmap = window.grab()
    ratio = pixmap.devicePixelRatio()
    pad = round(24 * ratio)
    image = wallpaper(pixmap.width() + 2 * pad, 180 * round(ratio), dark)
    painter = QPainter(image)
    painter.drawPixmap(pad, pad, pixmap)
    painter.end()
    return image


def sheet(items: list[tuple[str, QImage]], columns: int, dark: bool) -> QImage:
    cell_w = max(image.width() for _, image in items)
    cell_h = max(image.height() for _, image in items) + 36
    rows = (len(items) + columns - 1) // columns
    canvas = QImage(cell_w * columns, cell_h * rows, QImage.Format.Format_ARGB32_Premultiplied)
    canvas.fill(QColor("#101012") if dark else QColor("#f4f4f6"))
    painter = QPainter(canvas)
    painter.setPen(QColor("#dddddd") if dark else QColor("#222222"))
    font = QFont()
    font.setPixelSize(22)
    painter.setFont(font)
    for index, (label, image) in enumerate(items):
        x = (index % columns) * cell_w
        y = (index // columns) * cell_h
        painter.drawText(QRectF(x + 12, y + 4, cell_w, 30), Qt.AlignmentFlag.AlignVCenter, label)
        painter.drawImage(x, y + 36, image)
    painter.end()
    return canvas


def run(output: Path) -> None:
    app = QApplication(sys.argv)
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="shazam-shots-"))
    cover_url = make_cover(work / "cover.png")

    controller = Controller(
        StubBackend(),
        StubRecognizer(),
        SettingsStore(work / "config.json"),
        ffmpeg_check=lambda: True,
    )
    window = MainWindow(controller, preferences=SystemPreferences)

    full = Track("Neon Harbor", "The Paper Satellites", cover_url)
    long = Track(
        "Dreaming in Monochrome (Extended Remastered Anniversary Mix)",
        "The Quiet Orchestra of Distant Lighthouses & Friends",
        cover_url,
    )
    cases: list[tuple[str, State, int]] = [
        ("idle", State(Phase.IDLE), 400),
        ("listening", State(Phase.LISTENING), 700),
        ("fingerprinting", State(Phase.FINGERPRINTING), 700),
        ("matching", State(Phase.MATCHING), 700),
        ("result", State(Phase.RESULT, track=full), 900),
        ("result-long-text", State(Phase.RESULT, track=long), 900),
        (
            "result-no-cover",
            State(Phase.RESULT, track=Track("Neon Harbor", "The Paper Satellites", None)),
            700,
        ),
        ("result-missing-fields", State(Phase.RESULT, track=Track(None, None, None)), 700),
        *[
            (f"error-{kind.name.lower().replace('_', '-')}", State(Phase.ERROR, error=kind), 700)
            for kind in ErrorKind
        ],
    ]

    window.present()
    for dark in (False, True):
        window.set_dark(dark)
        suffix = "dark" if dark else "light"
        shots: list[tuple[str, QImage]] = []
        for name, state, wait in cases:
            window.apply_state(State(Phase.IDLE))
            settle(450)
            window.apply_state(state)
            settle(wait, tick=level_feed(window))
            image = composite(window, dark)
            image.save(str(output / f"{name}-{suffix}.png"))
            shots.append((name, image))

        window.apply_state(State(Phase.RESULT, track=full))
        settle(900)
        for field in window.findChildren(CopyField):
            field.copy()
            break
        settle(150)
        copied = composite(window, dark)
        copied.save(str(output / f"result-copied-{suffix}.png"))
        shots.append(("result-copied", copied))

        menu = SourceMenu(controller)
        menu.refresh()
        menu_image = menu.grab().toImage()
        menu_image.save(str(output / f"source-menu-{suffix}.png"))

        sheet(shots, columns=3, dark=dark).save(str(output / f"sheet-{suffix}.png"))

    opaque = MainWindow(controller, preferences=lambda: SystemPreferences(reduce_transparency=True))
    opaque.present()
    opaque.set_dark(True)
    opaque.apply_state(State(Phase.RESULT, track=full))
    settle(900)
    composite(opaque, True).save(str(output / "result-reduce-transparency-dark.png"))
    app.quit()


if __name__ == "__main__":
    run(Path(sys.argv[1]) if len(sys.argv) > 1 else Path("screenshots"))
