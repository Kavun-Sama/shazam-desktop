"""Generate the application icon set from the geometry below.

Writes ``assets/icon``: mark and tile SVGs, ``icon-1024.png``, ``icon.ico`` (Windows) and
``icon.icns`` (macOS), and the README banners ``assets/banner-{light,dark}.svg``.
Needs the ``icons`` extra (``pip install -e ".[icons]"``).

    python scripts/build_icons.py
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icon"


@dataclass(frozen=True)
class Layout:
    """The mark on a 256 grid: a "listening" dot followed by a sound wave.

    ``dot`` is ``(cx, cy, r)``, each bar is ``(x, y, height)``; bars are ``width`` wide,
    which equals the dot diameter.
    """

    dot: tuple[float, float, float]
    bars: tuple[tuple[float, float, float], ...]
    width: float
    scale: float  # size of the mark on the 1024 tile, relative to its 256 grid


FULL = Layout(
    dot=(24, 128, 16),
    bars=((60, 80, 96), (112, 24, 208), (164, 64, 128), (216, 104, 48)),
    width=32,
    scale=2.1,
)
# Drawn for 16-32 px: fewer, heavier elements so the gaps survive.
SMALL = Layout(
    dot=(32, 128, 20),
    bars=((76, 68, 120), (140, 16, 224), (204, 72, 112)),
    width=40,
    scale=2.15,
)
SMALL_SIZES = (16, 20, 24, 32)

GRADIENT = (("0", "#8F5BFF"), ("0.55", "#C24DD8"), ("1", "#FF5C8D"))
TILE = {"mac": (100, 824, 185), "win": (32, 960, 215)}  # inset, size, corner radius


def _pill(x: float, y: float, width: float, height: float) -> str:
    r = width / 2
    return (
        f"M{x:g} {y + r:g}A{r:g} {r:g} 0 0 1 {x + width:g} {y + r:g}"
        f"V{y + height - r:g}A{r:g} {r:g} 0 0 1 {x:g} {y + height - r:g}Z"
    )


def _mark_path(layout: Layout, scale: float, cx: float, cy: float) -> str:
    """One compound path for the whole mark, centred on ``(cx, cy)`` at ``scale``."""

    def at(x: float, y: float) -> tuple[float, float]:
        return cx + (x - 128) * scale, cy + (y - 128) * scale

    dot_x, dot_y, dot_r = layout.dot
    px, py = at(dot_x, dot_y)
    r = dot_r * scale
    parts = [
        f"M{px - r:.3f} {py:.3f}a{r:.3f} {r:.3f} 0 1 0 {2 * r:.3f} 0"
        f"a{r:.3f} {r:.3f} 0 1 0 {-2 * r:.3f} 0Z"
    ]
    for x, y, height in layout.bars:
        bx, by = at(x, y)
        parts.append(_pill(round(bx, 3), round(by, 3), layout.width * scale, height * scale))
    return "".join(parts)


def mark_svg(color: str = "#000") -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
        "<title>Shazam Desktop mark</title>"
        f'<path fill="{color}" d="{_mark_path(FULL, 1, 128, 128)}"/></svg>\n'
    )


def _tile_body(kind: str, small: bool = False) -> str:
    """Gradient definitions and shapes of the icon tile, in 1024 px coordinates."""
    inset, size, radius = TILE[kind]
    layout = SMALL if small else FULL
    stops = "".join(f'<stop offset="{o}" stop-color="{c}"/>' for o, c in GRADIENT)
    low, high = inset + size * 0.05, inset + size * 0.95
    tile = f'x="{inset}" y="{inset}" width="{size}" height="{size}" rx="{radius}"'
    mark = _mark_path(layout, layout.scale * size / 824, 512, 506)
    return (
        "<defs>"
        f'<linearGradient id="bg" x1="{low:g}" y1="{low:g}" x2="{high:g}" y2="{high:g}" '
        f'gradientUnits="userSpaceOnUse">{stops}</linearGradient>'
        f'<linearGradient id="sheen" x1="0" y1="{inset}" x2="0" y2="{inset + size * 0.6:g}" '
        'gradientUnits="userSpaceOnUse"><stop offset="0" stop-color="#fff" stop-opacity=".22"/>'
        '<stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient></defs>'
        f'<rect {tile} fill="url(#bg)"/><rect {tile} fill="url(#sheen)"/>'
        f'<path fill="#fff" d="{mark}"/>'
    )


def tile_svg(kind: str, small: bool = False) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1024 1024" '
        'width="1024" height="1024"><title>Shazam Desktop</title>'
        f"{_tile_body(kind, small)}</svg>\n"
    )


BANNER = {
    # background gradient stops, bar colour and opacity
    "light": (("#C7B6FF", "#F2B5DA", "#FFD2A6"), "#FFFFFF", 0.42),
    "dark": (("#1A1033", "#3B1757", "#5C1E49"), "#FFFFFF", 0.10),
}
BANNER_WIDTH, BANNER_HEIGHT, BANNER_TILE = 1280, 360, 176


def banner_svg(theme: str) -> str:
    """Wide README header: the app icon over a field of sound bars."""
    stops, bar_color, bar_opacity = BANNER[theme]
    gradient = "".join(
        f'<stop offset="{o}" stop-color="{c}"/>'
        for o, c in zip(("0", "0.55", "1"), stops, strict=True)
    )
    bars = []
    pitch, width, centre = 28, 14, BANNER_HEIGHT / 2
    count = BANNER_WIDTH // pitch
    for index in range(count + 1):
        x = index * pitch + (BANNER_WIDTH - count * pitch) / 2
        phase = index / count
        envelope = math.sin(math.pi * phase) ** 1.4
        wobble = 0.55 + 0.45 * abs(math.sin(index * 0.83) * math.cos(index * 0.37 + 0.6))
        height = max(width, 250 * envelope * wobble)
        bars.append(_pill(round(x, 2), round(centre - height / 2, 2), width, round(height, 2)))
    tile_x, tile_y = (BANNER_WIDTH - BANNER_TILE) / 2, (BANNER_HEIGHT - BANNER_TILE) / 2
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {BANNER_WIDTH} {BANNER_HEIGHT}" '
        f'width="{BANNER_WIDTH}" height="{BANNER_HEIGHT}" role="img" aria-label="Shazam Desktop">'
        "<title>Shazam Desktop</title><defs>"
        f'<linearGradient id="field" x1="0" y1="0" x2="{BANNER_WIDTH}" y2="{BANNER_HEIGHT}" '
        f'gradientUnits="userSpaceOnUse">{gradient}</linearGradient>'
        '<filter id="lift" x="-30%" y="-30%" width="160%" height="170%">'
        '<feDropShadow dx="0" dy="14" stdDeviation="16" flood-color="#2A0F55" flood-opacity=".38"/>'
        "</filter></defs>"
        f'<rect width="{BANNER_WIDTH}" height="{BANNER_HEIGHT}" fill="url(#field)"/>'
        f'<path fill="{bar_color}" fill-opacity="{bar_opacity}" d="{"".join(bars)}"/>'
        f'<g filter="url(#lift)"><svg x="{tile_x:g}" y="{tile_y:g}" width="{BANNER_TILE}" '
        f'height="{BANNER_TILE}" viewBox="100 100 824 824">{_tile_body("mac")}</svg></g>'
        "</svg>\n"
    )


def main() -> None:
    import cairosvg  # type: ignore[import-untyped]
    from PIL import Image

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "mark.svg").write_text(mark_svg(), encoding="utf-8")
    (OUT / "mark-white.svg").write_text(mark_svg("#fff"), encoding="utf-8")
    (OUT / "icon-macos.svg").write_text(tile_svg("mac"), encoding="utf-8")
    (OUT / "icon-windows.svg").write_text(tile_svg("win"), encoding="utf-8")

    def render(kind: str, size: int) -> Image.Image:
        svg = tile_svg(kind, small=size in SMALL_SIZES)
        png = cairosvg.svg2png(bytestring=svg.encode(), output_width=size, output_height=size)
        return Image.open(io.BytesIO(png)).convert("RGBA")

    for theme in BANNER:
        (OUT.parent / f"banner-{theme}.svg").write_text(banner_svg(theme), encoding="utf-8")

    sizes = (256, 16, 20, 24, 32, 40, 48, 64, 128)  # the first image is the base frame
    win = [render("win", size) for size in sizes]
    win[0].save(OUT / "icon.ico", sizes=[(s, s) for s in sizes], append_images=win[1:])
    mac = render("mac", 1024)
    mac.save(OUT / "icon-1024.png")
    mac.save(
        OUT / "icon.icns",
        sizes=[(s, s) for s in (16, 32, 64, 128, 256, 512, 1024)],
        append_images=[render("mac", s) for s in (16, 32, 64, 128, 256, 512)],
    )
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
