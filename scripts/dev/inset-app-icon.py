#!/usr/bin/env python3
"""Generate macOS Dock app icons with baked superellipse squircle (native macOS spec)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

# Apple Developer Forums #670578: 824x824 face on 1024 canvas → halved for 512 master.
CANVAS = 512
FACE_SIZE = 412
GUTTER = 50
SQUIRCLE_EXPONENT = 5.0
# Higher-contrast brand gradient (replaces low-contrast pastel wash).
GRADIENT_TOP = (72, 138, 196)
GRADIENT_BOTTOM = (242, 128, 72)
BACKGROUND_TOLERANCE = 48


def squircle_mask(size: int, exponent: float = SQUIRCLE_EXPONENT) -> Image.Image:
    """macOS continuous-curvature superellipse (|x|^n + |y|^n <= 1)."""
    mask = Image.new("L", (size, size), 0)
    pixels = mask.load()
    center = (size - 1) / 2
    radius = size / 2
    for y in range(size):
        ny = abs(y - center) / radius
        ny_term = ny**exponent
        for x in range(size):
            nx = abs(x - center) / radius
            if nx**exponent + ny_term <= 1.0:
                pixels[x, y] = 255
    return mask


def vertical_gradient(size: int, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for y in range(size):
        t = y / max(size - 1, 1)
        color = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line((0, y, size - 1, y), fill=color)
    return img.convert("RGBA")


def average_corner_rgb(image: Image.Image) -> tuple[int, int, int]:
    px = image.load()
    width, height = image.size
    samples = [
        px[0, 0][:3],
        px[width - 1, 0][:3],
        px[0, height - 1][:3],
        px[width - 1, height - 1][:3],
    ]
    return tuple(sum(channel[i] for channel in samples) // 4 for i in range(3))


def strip_background(art: Image.Image, tolerance: int = BACKGROUND_TOLERANCE) -> Image.Image:
    bg = average_corner_rgb(art)
    out = art.copy()
    px = out.load()
    for y in range(out.height):
        for x in range(out.width):
            r, g, b, a = px[x, y]
            dist = (abs(r - bg[0]) + abs(g - bg[1]) + abs(b - bg[2])) // 3
            if dist <= tolerance:
                px[x, y] = (r, g, b, 0)
    return out


def fit_foreground(source: Image.Image, max_size: int) -> Image.Image:
    foreground = strip_background(source)
    bbox = foreground.getbbox() or (0, 0, source.width, source.height)
    art = foreground.crop(bbox)
    width, height = art.size
    scale = min(max_size / width, max_size / height)
    fitted = art.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (max_size, max_size), (0, 0, 0, 0))
    offset = ((max_size - fitted.width) // 2, (max_size - fitted.height) // 2)
    canvas.paste(fitted, offset, fitted)
    return canvas


def make_dock_icon(source: Path) -> Image.Image:
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)

    face = vertical_gradient(FACE_SIZE, GRADIENT_TOP, GRADIENT_BOTTOM)
    foreground = fit_foreground(src, FACE_SIZE)
    face = Image.alpha_composite(face, foreground)

    mask = squircle_mask(FACE_SIZE)
    alpha = Image.composite(face.split()[3], Image.new("L", (FACE_SIZE, FACE_SIZE), 0), mask)
    face.putalpha(alpha)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(face, (GUTTER, GUTTER), face)
    return canvas


def export_png_sizes(master: Path, outputs: dict[int, Path]) -> None:
    base = Image.open(master).convert("RGBA")
    for size, path in outputs.items():
        img = base if size == CANVAS else base.resize((size, size), Image.Resampling.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, optimize=True)


def export_webp_from_image(img: Image.Image, dest: Path, quality: int = 86) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(dest, format="WEBP", quality=quality, method=6)


def export_tray_icons(source: Path, icons_dir: Path) -> None:
    """Pure black template glyph on fully transparent background for macOS menu bar."""
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)

    foreground = strip_background(src)
    bbox = foreground.getbbox()
    if bbox is None:
        return

    art = foreground.crop(bbox)
    for size, name in ((22, "tray_icon.png"), (44, "tray_icon@2x.png")):
        pad = 1
        inner = size - 2 * pad
        fitted = art.resize((inner, inner), Image.Resampling.LANCZOS)
        alpha = fitted.split()[3].point(lambda value: 255 if value > 48 else 0)
        icon = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        glyph = Image.new("RGBA", (inner, inner), (0, 0, 0, 255))
        glyph.putalpha(alpha)
        icon.paste(glyph, (pad, pad), glyph)
        icon.save(icons_dir / name, optimize=True)


def resolve_source(repo: Path) -> Path:
    git_src = repo / "myrm-agent-frontend/public/brand/.logo-icon-source-512.png"
    if not git_src.exists():
        result = subprocess.run(
            [
                "git",
                "show",
                "3cd833c:myrm-agent-frontend/public/brand/logo-icon-512.png",
            ],
            cwd=repo,
            capture_output=True,
        )
        if result.returncode == 0 and result.stdout:
            git_src.write_bytes(result.stdout)

    candidates = [
        git_src,
        repo / "myrm-agent-frontend/public/brand/logo-icon-512.png",
        repo / "myrm-agent-desktop/src-tauri/icons/icon.png",
    ]
    for path in candidates:
        if path.exists() and path.stat().st_size > 0:
            return path
    raise FileNotFoundError("No source icon found")


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    source = resolve_source(repo)
    master = repo / "myrm-agent-frontend/public/brand/logo-icon-512-macos.png"
    icon = make_dock_icon(source)
    master.parent.mkdir(parents=True, exist_ok=True)
    icon.save(master, optimize=True)

    brand = repo / "myrm-agent-frontend/public/brand"
    icons = repo / "myrm-agent-frontend/public/icons"
    tauri_icons = repo / "myrm-agent-desktop/src-tauri/icons"

    png_map: dict[int, list[Path]] = {
        32: [brand / "logo-icon-32.png", icons / "icon-32x32.png"],
        64: [brand / "logo-icon-64.png"],
        192: [brand / "logo-icon-192.png", icons / "icon-192x192.png"],
        512: [
            brand / "logo-icon.png",
            brand / "logo-icon-512.png",
            icons / "icon-512x512.png",
            tauri_icons / "icon.png",
        ],
    }

    for size, paths in png_map.items():
        export_png_sizes(master, {size: paths[0]})
        for extra in paths[1:]:
            extra.write_bytes(paths[0].read_bytes())

    export_webp_from_image(icon, brand / "logo-icon.webp")
    export_webp_from_image(
        icon.resize((128, 128), Image.Resampling.LANCZOS),
        brand / "logo-icon-128.webp",
    )
    export_webp_from_image(
        icon.resize((80, 80), Image.Resampling.LANCZOS),
        brand / "logo-icon-80.webp",
    )

    subprocess.run(
        ["cargo", "tauri", "icon", str(master)],
        cwd=repo / "myrm-agent-desktop",
        check=True,
    )

    master.unlink(missing_ok=True)
    export_tray_icons(source, tauri_icons)
    git_src = repo / "myrm-agent-frontend/public/brand/.logo-icon-source-512.png"
    git_src.unlink(missing_ok=True)
    print(f"OK: high-contrast squircle icon from {source} face={FACE_SIZE}px gutter={GUTTER}px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
