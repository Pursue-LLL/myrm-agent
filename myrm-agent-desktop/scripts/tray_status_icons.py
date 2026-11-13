"""The tray icon set: a black template glyph and its busy and degraded variants.

A macOS template icon is drawn from its alpha channel alone, so a status badge in the glyph's bottom-right
corner has to read by silhouette: a disc for busy, a triangle for degraded. A transparent halo around the
badge keeps it from merging into the glyph. The badge colours still matter on platforms that draw the
pixels as they are.
"""

from __future__ import annotations

from collections.abc import Callable
from math import dist, sqrt
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

# The menu bar icon at 2x; the tray loads only this size.
TRAY_ICON_SIZE = 44
GLYPH_PAD = 1
# Glyph pixels at least this opaque are drawn fully opaque, which keeps the template edges crisp.
ALPHA_CUTOFF = 48
# Pixel sizes on the 44 px canvas.
BADGE_RADIUS = 7.0
HALO_WIDTH = 2.0
BUSY_COLOR = (34, 197, 94)
DEGRADED_COLOR = (245, 158, 11)
# Shapes are painted at this multiple of the canvas and averaged down, which anti-aliases their edges.
SUPERSAMPLE = 8

Point = tuple[float, float]
Painter = Callable[[ImageDraw.ImageDraw], None]


def _scaled(point: Point) -> Point:
    """The centre of a canvas pixel on the supersampled canvas."""
    return (point[0] + 0.5) * SUPERSAMPLE, (point[1] + 0.5) * SUPERSAMPLE


def _coverage(size: int, paint: Painter) -> Image.Image:
    """How much of each canvas pixel a shape covers, as an 8-bit mask."""
    big = Image.new("L", (size * SUPERSAMPLE, size * SUPERSAMPLE), 0)
    paint(ImageDraw.Draw(big))
    return big.resize((size, size), Image.Resampling.BOX)


def _disc(centre: Point, radius: float) -> Painter:
    def paint(draw: ImageDraw.ImageDraw) -> None:
        draw.ellipse(
            [*_scaled((centre[0] - radius, centre[1] - radius)), *_scaled((centre[0] + radius, centre[1] + radius))], fill=255
        )

    return paint


def _triangle(vertices: list[Point]) -> Painter:
    def paint(draw: ImageDraw.ImageDraw) -> None:
        draw.polygon([_scaled(vertex) for vertex in vertices], fill=255)

    return paint


def _grown(vertices: list[Point], margin: float) -> list[Point]:
    """The triangle with every edge pushed outwards by `margin`, found by scaling about the incentre."""
    a, b, c = (dist(vertices[(i + 1) % 3], vertices[(i + 2) % 3]) for i in range(3))
    half_perimeter = (a + b + c) / 2
    inradius = sqrt(half_perimeter * (half_perimeter - a) * (half_perimeter - b) * (half_perimeter - c)) / half_perimeter
    incentre = tuple((a * vertices[0][k] + b * vertices[1][k] + c * vertices[2][k]) / (a + b + c) for k in (0, 1))
    factor = 1 + margin / inradius
    return [(incentre[0] + (x - incentre[0]) * factor, incentre[1] + (y - incentre[1]) * factor) for x, y in vertices]


def _with_badge(glyph: Image.Image, badge: Painter, halo: Painter, color: tuple[int, int, int]) -> Image.Image:
    """The glyph with the halo cleared out of it and the coloured badge on top."""
    size = glyph.width
    cleared = glyph.copy()
    cleared.putalpha(ImageChops.multiply(glyph.getchannel("A"), ImageChops.invert(_coverage(size, halo))))
    layer = Image.new("RGBA", glyph.size, (*color, 0))
    layer.putalpha(_coverage(size, badge))
    return Image.alpha_composite(cleared, layer)


def _status_icons(idle: Image.Image) -> dict[str, Image.Image]:
    """The busy and degraded variants of a square idle glyph, keyed by status name."""
    if idle.width != idle.height:
        raise ValueError("the idle tray glyph must be square")
    glyph = idle.convert("RGBA")
    # Flush with the bottom-right corner of the canvas.
    cx = cy = glyph.width - 1 - BADGE_RADIUS
    triangle = [
        (cx, cy - 1.1 * BADGE_RADIUS),
        (cx + 1.05 * BADGE_RADIUS, cy + 0.8 * BADGE_RADIUS),
        (cx - 1.05 * BADGE_RADIUS, cy + 0.8 * BADGE_RADIUS),
    ]
    return {
        "busy": _with_badge(glyph, _disc((cx, cy), BADGE_RADIUS), _disc((cx, cy), BADGE_RADIUS + HALO_WIDTH), BUSY_COLOR),
        "degraded": _with_badge(glyph, _triangle(triangle), _triangle(_grown(triangle, HALO_WIDTH)), DEGRADED_COLOR),
    }


def write_tray_icons(artwork: Image.Image, icons_dir: Path) -> None:
    """Write `tray_icon@2x.png` and its `busy` and `degraded` variants from the brand mark's foreground layer."""
    bbox = artwork.getbbox()
    if bbox is None:
        return
    inner = TRAY_ICON_SIZE - 2 * GLYPH_PAD
    fitted = artwork.crop(bbox).resize((inner, inner), Image.Resampling.LANCZOS)
    glyph = Image.new("RGBA", (inner, inner), (0, 0, 0, 255))
    glyph.putalpha(fitted.getchannel("A").point(lambda value: 255 if value > ALPHA_CUTOFF else 0))
    idle = Image.new("RGBA", (TRAY_ICON_SIZE, TRAY_ICON_SIZE), (0, 0, 0, 0))
    idle.paste(glyph, (GLYPH_PAD, GLYPH_PAD), glyph)

    idle.save(icons_dir / "tray_icon@2x.png", optimize=True)
    for status, icon in _status_icons(idle).items():
        icon.save(icons_dir / f"tray_icon_{status}@2x.png", optimize=True)
