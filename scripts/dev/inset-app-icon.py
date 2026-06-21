#!/usr/bin/env python3
"""Generate MyrmAgent icon assets (three classes, never mixed):

1. App/PWA  — public/icons/* + tauri/icons/icon.*  (squircle gradient + illustration)
2. Brand UI — public/brand/brand-mark-128.webp     (transparent mark from brand-mark-source-512.png)
3. Tray     — tauri/icons/tray_icon*.png           (black template from brand-mark-source-512.png)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Apple Developer Forums #670578: 824x824 face on 1024 canvas → halved for 512 master.
CANVAS = 512
FACE_SIZE = 412
GUTTER = 50
SQUIRCLE_EXPONENT = 5.0
# App icon squircle face: orange (left) → blue (right).
FACE_GRADIENT_LEFT = (242, 128, 72)
FACE_GRADIENT_RIGHT = (72, 138, 196)
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


def horizontal_gradient(size: int, left: tuple[int, int, int], right: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for x in range(size):
        t = x / max(size - 1, 1)
        color = tuple(int(left[i] + (right[i] - left[i]) * t) for i in range(3))
        draw.line((x, 0, x, size - 1), fill=color)
    return img.convert("RGBA")


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


def has_transparent_corners(image: Image.Image) -> bool:
    width, height = image.size
    corners = (
        image.getpixel((0, 0))[3],
        image.getpixel((width - 1, 0))[3],
        image.getpixel((0, height - 1))[3],
        image.getpixel((width - 1, height - 1))[3],
    )
    return all(alpha < 16 for alpha in corners)


def fit_foreground_layer(source: Image.Image, max_size: int) -> Image.Image:
    """Place foreground on transparent canvas; alpha-aware when corners are already transparent."""
    src = source.convert("RGBA")
    if has_transparent_corners(src):
        art = src
    else:
        art = strip_background(src)

    bbox = art.getbbox()
    if bbox is None:
        return Image.new("RGBA", (max_size, max_size), (0, 0, 0, 0))

    cropped = art.crop(bbox)
    width, height = cropped.size
    scale = min(max_size / width, max_size / height)
    fitted = cropped.resize(
        (max(1, round(width * scale)), max(1, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    canvas = Image.new("RGBA", (max_size, max_size), (0, 0, 0, 0))
    offset = ((max_size - fitted.width) // 2, (max_size - fitted.height) // 2)
    canvas.paste(fitted, offset, fitted)
    return canvas


def add_macos_squircle_depth(face: Image.Image, size: int) -> Image.Image:
    """Whole-icon depth: top gloss + bottom inner shade on the squircle face (not the mark)."""
    mask = squircle_mask(size)
    mask_px = mask.load()
    out = face.copy()
    px = out.load()

    for y in range(size):
        ny = y / max(size - 1, 1)
        for x in range(size):
            if mask_px[x, y] == 0:
                continue
            r, g, b, a = px[x, y]
            nx = x / max(size - 1, 1)

            # Top gloss (whole face)
            top = max(0.0, 1.0 - ny * 2.2)
            gloss = int(52 * top * top)
            r = min(255, r + gloss)
            g = min(255, g + gloss)
            b = min(255, b + gloss)

            # Bottom-inner shade (whole face)
            bottom = max(0.0, (ny - 0.55) * 2.2)
            shade = int(36 * bottom)
            r = max(0, r - shade)
            g = max(0, g - shade)
            b = max(0, b - shade)

            # Left-top rim catchlight / right-bottom rim shade
            rim_light = max(0.0, 1.0 - (nx * 0.4 + ny * 0.6)) * 0.35
            rim_dark = max(0.0, (nx * 0.35 + ny * 0.65) - 0.45) * 0.45
            r = min(255, max(0, int(r + rim_light * 40 - rim_dark * 40)))
            g = min(255, max(0, int(g + rim_light * 40 - rim_dark * 40)))
            b = min(255, max(0, int(b + rim_light * 40 - rim_dark * 40)))

            px[x, y] = (r, g, b, a)

    return out


def add_outer_icon_shadow(canvas: Image.Image, blur_radius: int = 14, y_offset: int = 10) -> Image.Image:
    """Soft shadow under the full squircle — visible even when Dock shadow is weak (dev builds)."""
    rgba = canvas.convert("RGBA")
    alpha = rgba.split()[3]
    shadow = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    shadow.putalpha(alpha.point(lambda value: min(255, int(value * 0.38))))
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur_radius))
    out = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    out.alpha_composite(shadow, (0, y_offset))
    out.alpha_composite(rgba, (0, 0))
    return out


def make_dock_icon(source: Path) -> Image.Image:
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)

    face = horizontal_gradient(FACE_SIZE, FACE_GRADIENT_LEFT, FACE_GRADIENT_RIGHT)
    foreground = fit_foreground_layer(src, FACE_SIZE)
    face = Image.alpha_composite(face, foreground)
    face = add_macos_squircle_depth(face, FACE_SIZE)

    mask = squircle_mask(FACE_SIZE)
    alpha = Image.composite(face.split()[3], Image.new("L", (FACE_SIZE, FACE_SIZE), 0), mask)
    face.putalpha(alpha)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(face, (GUTTER, GUTTER), face)
    return add_outer_icon_shadow(canvas)


def export_png_sizes(master: Path, outputs: dict[int, Path]) -> None:
    base = Image.open(master).convert("RGBA")
    for size, path in outputs.items():
        img = base if size == CANVAS else base.resize((size, size), Image.Resampling.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, optimize=True)


def export_webp_from_image(img: Image.Image, dest: Path, quality: int = 86) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(dest, format="WEBP", quality=quality, method=6)


def export_favicon(brand_dir: Path, public_dir: Path) -> None:
    """Browser tab icons — PNG primary (sharp), ICO fallback."""
    for name in ("brand-mark-source-1024.png", "brand-mark-source-512.png"):
        candidate = brand_dir / name
        if candidate.exists() and candidate.stat().st_size > 0:
            src = Image.open(candidate).convert("RGBA")
            break
    else:
        raise FileNotFoundError("brand-mark-source-1024.png or brand-mark-source-512.png required")

    bbox = src.getbbox()
    art = src.crop(bbox) if bbox else src

    def render(size: int) -> Image.Image:
        pad = max(0, round(size * 0.04))
        inner = size - 2 * pad
        scale = min(inner / art.width, inner / art.height)
        fitted = art.resize(
            (max(1, round(art.width * scale)), max(1, round(art.height * scale))),
            Image.Resampling.LANCZOS,
        )
        if size <= 48:
            fitted = fitted.filter(ImageFilter.UnsharpMask(radius=0.8, percent=130, threshold=2))
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        offset = ((size - fitted.width) // 2, (size - fitted.height) // 2)
        canvas.paste(fitted, offset, fitted)
        return canvas

    png_sizes = (32, 48, 64)
    png_images = {size: render(size) for size in png_sizes}
    for size, image in png_images.items():
        image.save(public_dir / f"favicon-{size}.png", optimize=True)

    icon16 = render(16)
    icon16.save(
        public_dir / "favicon.ico",
        format="ICO",
        sizes=[(16, 16), (32, 32), (48, 48)],
        append_images=[png_images[32], png_images[48]],
    )


def export_brand_mark(source: Path, brand: Path) -> None:
    """UI exports — preserve full source framing (no bbox crop)."""
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)
    for size, name in ((128, "brand-mark-128.webp"), (256, "brand-mark-256.webp")):
        export_webp_from_image(
            src.resize((size, size), Image.Resampling.LANCZOS),
            brand / name,
            quality=92,
        )


def export_tray_icons(source: Path, icons_dir: Path) -> None:
    """Pure black template glyph on fully transparent background for macOS menu bar."""
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)

    layer = fit_foreground_layer(src, CANVAS)
    bbox = layer.getbbox()
    if bbox is None:
        return

    art = layer.crop(bbox)
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


def resolve_mark_source(repo: Path) -> Path:
    brand = repo / "myrm-agent-frontend/public/brand"
    for name in ("brand-mark-source-1024.png", "brand-mark-source-512.png"):
        path = brand / name
        if path.exists() and path.stat().st_size > 0:
            return path
    raise FileNotFoundError("brand-mark-source-1024.png or brand-mark-source-512.png required")


def resolve_brand_mark_source(repo: Path) -> Path:
    return resolve_mark_source(repo)


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    mark_source = resolve_mark_source(repo)
    master = repo / "myrm-agent-frontend/public/icons/.app-icon-master-512-macos.png"
    icon = make_dock_icon(mark_source)
    master.parent.mkdir(parents=True, exist_ok=True)
    icon.save(master, optimize=True)

    brand = repo / "myrm-agent-frontend/public/brand"
    icons = repo / "myrm-agent-frontend/public/icons"
    tauri_icons = repo / "myrm-agent-desktop/src-tauri/icons"

    export_brand_mark(mark_source, brand)

    png_map: dict[int, list[Path]] = {
        32: [icons / "icon-32x32.png"],
        192: [icons / "icon-192x192.png"],
        512: [icons / "icon-512x512.png", tauri_icons / "icon.png"],
    }

    for size, paths in png_map.items():
        export_png_sizes(master, {size: paths[0]})
        for extra in paths[1:]:
            extra.write_bytes(paths[0].read_bytes())

    export_favicon(brand, repo / "myrm-agent-frontend/public")

    subprocess.run(
        ["cargo", "tauri", "icon", str(master)],
        cwd=repo / "myrm-agent-desktop",
        check=True,
    )

    master.unlink(missing_ok=True)
    export_tray_icons(mark_source, tauri_icons)
    print(
        f"OK: all icons from {mark_source.name}; "
        f"app/PWA squircle + brand {{128,256}} webp + tray; face={FACE_SIZE}px gutter={GUTTER}px"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
