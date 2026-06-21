#!/usr/bin/env python3
"""Generate MyrmAgent icon assets (three classes, never mixed):

1. App/PWA  — public/icons/* + tauri/icons/icon.*  (squircle gradient + illustration)
2. Brand UI — public/brand/brand-mark-128.webp     (transparent mark from brand-mark-source-512.png)
3. Tray     — tauri/icons/tray_icon*.png           (black template from brand-mark-source-512.png)
"""

from __future__ import annotations

import subprocess
from colorsys import hls_to_rgb, rgb_to_hls
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

# Apple Icon Composer grid: 824×824 enclosure centered on 1024 (gutter 100px).
MASTER_CANVAS = 1024
ENCLOSURE_SIZE = 824
GUTTER = (MASTER_CANVAS - ENCLOSURE_SIZE) // 2
SQUIRCLE_EXPONENT = 5.0
SQUIRCLE_SUPERSAMPLE = 4
# ~80% safe-zone art inset inside enclosure (HIG / Icon Composer convention).
ART_INSET_RATIO = 0.80
ICON_MARK_SCALE = 1.12
BRAND_CANVAS = 512
# App icon squircle face: orange (left) → blue (right).
FACE_GRADIENT_BL = (242, 128, 72)
FACE_GRADIENT_TR = (72, 138, 196)
BACKGROUND_TOLERANCE = 48


def squircle_mask_pixel(size: int, exponent: float = SQUIRCLE_EXPONENT) -> Image.Image:
    """Raw superellipse raster (|x|^n + |y|^n <= 1) — quintic matches Apple Dock."""
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


def squircle_mask(size: int, exponent: float = SQUIRCLE_EXPONENT) -> Image.Image:
    """Supersampled squircle — anti-aliases edge to match native macOS icons."""
    if SQUIRCLE_SUPERSAMPLE <= 1:
        return squircle_mask_pixel(size, exponent)
    big = squircle_mask_pixel(size * SQUIRCLE_SUPERSAMPLE, exponent)
    return big.resize((size, size), Image.Resampling.LANCZOS)


GRADIENT_SATURATION = 0.80
GRADIENT_LIGHTNESS = 0.78


def pastel_brand_color(rgb: tuple[int, int, int]) -> tuple[int, int, int]:
    """Light pastel: preserve orange/blue hue only (no white channel mix)."""
    r, g, b = (ch / 255.0 for ch in rgb)
    hue, _, _ = rgb_to_hls(r, g, b)
    pr, pg, pb = hls_to_rgb(hue, GRADIENT_LIGHTNESS, GRADIENT_SATURATION)
    return tuple(int(ch * 255) for ch in (pr, pg, pb))


def raw_horizontal_gradient(size: int, left: tuple[int, int, int], right: tuple[int, int, int]) -> Image.Image:
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for x in range(size):
        t = x / max(size - 1, 1)
        color = tuple(int(left[i] + (right[i] - left[i]) * t) for i in range(3))
        draw.line((x, 0, x, size - 1), fill=color)
    return img.convert("RGBA")


def horizontal_gradient(size: int, left: tuple[int, int, int], right: tuple[int, int, int]) -> Image.Image:
    left = pastel_brand_color(left)
    right = pastel_brand_color(right)
    img = Image.new("RGB", (size, size))
    draw = ImageDraw.Draw(img)
    for x in range(size):
        t = x / max(size - 1, 1)
        color = tuple(int(left[i] + (right[i] - left[i]) * t) for i in range(3))
        draw.line((x, 0, x, size - 1), fill=color)
    return img.convert("RGBA")


def brand_face_gradient(size: int, bl: tuple[int, int, int], tr: tuple[int, int, int]) -> Image.Image:
    """Bottom-left → top-right brand gradient with subtle vertical lighting."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    denom = max(size - 1, 1)
    for y in range(size):
        for x in range(size):
            t = (x / denom + (1.0 - y / denom)) / 2.0
            color = tuple(int(bl[i] + (tr[i] - bl[i]) * t) for i in range(3))
            px[x, y] = color
    rgba = img.convert("RGBA")
    px_rgba = rgba.load()
    for y in range(size):
        vy = 1.0 - (y / denom) * 0.16 + 0.08
        for x in range(size):
            r, g, b, a = px_rgba[x, y]
            px_rgba[x, y] = (
                min(255, max(0, int(r * vy))),
                min(255, max(0, int(g * vy))),
                min(255, max(0, int(b * vy))),
                a,
            )
    return rgba


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


def deepen_top_right_corner(face: Image.Image, strength: float = 0.22, radius_ratio: float = 0.38) -> Image.Image:
    """Only top-right corner — deeper blue for mark contrast; rest of gradient unchanged."""
    out = face.copy()
    px = out.load()
    width, height = out.size
    denom_x = max(width - 1, 1)
    denom_y = max(height - 1, 1)
    for y in range(height):
        ty = y / denom_y
        for x in range(width):
            tx = x / denom_x
            dx = 1.0 - tx
            dy = ty
            dist = (dx * dx + dy * dy) ** 0.5
            weight = max(0.0, 1.0 - dist / radius_ratio) ** 1.8
            factor = 1.0 - strength * weight
            r, g, b, a = px[x, y]
            px[x, y] = (
                max(0, int(r * factor)),
                max(0, int(g * factor)),
                max(0, int(b * factor)),
                a,
            )
    return out


def add_macos_squircle_depth(face: Image.Image, size: int) -> Image.Image:
    """Squircle face depth: top specular + bottom inner shade + rim (mark untouched)."""
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

            bottom = max(0.0, (ny - 0.55) * 2.2)
            shade = int(40 * bottom)
            r = max(0, r - shade)
            g = max(0, g - shade)
            b = max(0, b - shade)

            rim_light = max(0.0, 1.0 - (nx * 0.4 + ny * 0.6)) * 0.35
            rim_dark = max(0.0, (nx * 0.35 + ny * 0.65) - 0.45) * 0.45
            r = min(255, max(0, int(r + rim_light * 35 - rim_dark * 35)))
            g = min(255, max(0, int(g + rim_light * 35 - rim_dark * 35)))
            b = min(255, max(0, int(b + rim_light * 35 - rim_dark * 35)))

            px[x, y] = (r, g, b, a)

    return out


def make_dock_icon(source: Path) -> Image.Image:
    src = Image.open(source).convert("RGBA")
    if src.size != (MASTER_CANVAS, MASTER_CANVAS):
        src = src.resize((MASTER_CANVAS, MASTER_CANVAS), Image.Resampling.LANCZOS)

    face = raw_horizontal_gradient(ENCLOSURE_SIZE, FACE_GRADIENT_BL, FACE_GRADIENT_TR)
    face = deepen_top_right_corner(face)
    face = add_macos_squircle_depth(face, ENCLOSURE_SIZE)
    art_max = int(ENCLOSURE_SIZE * ART_INSET_RATIO * ICON_MARK_SCALE)
    foreground_layer = fit_foreground_layer(src, art_max)
    foreground = Image.new("RGBA", (ENCLOSURE_SIZE, ENCLOSURE_SIZE), (0, 0, 0, 0))
    inset = (ENCLOSURE_SIZE - art_max) // 2
    foreground.paste(foreground_layer, (inset, inset), foreground_layer)
    face = Image.alpha_composite(face, foreground)

    mask = squircle_mask(ENCLOSURE_SIZE)
    alpha = Image.composite(face.split()[3], Image.new("L", (ENCLOSURE_SIZE, ENCLOSURE_SIZE), 0), mask)
    face.putalpha(alpha)

    canvas = Image.new("RGBA", (MASTER_CANVAS, MASTER_CANVAS), (0, 0, 0, 0))
    canvas.paste(face, (GUTTER, GUTTER), face)
    return canvas


def export_png_sizes(master: Path, outputs: dict[int, Path]) -> None:
    base = Image.open(master).convert("RGBA")
    for size, path in outputs.items():
        img = base if size == MASTER_CANVAS else base.resize((size, size), Image.Resampling.LANCZOS)
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
    if src.size != (BRAND_CANVAS, BRAND_CANVAS):
        src = src.resize((BRAND_CANVAS, BRAND_CANVAS), Image.Resampling.LANCZOS)
    for size, name in ((128, "brand-mark-128.webp"), (256, "brand-mark-256.webp")):
        export_webp_from_image(
            src.resize((size, size), Image.Resampling.LANCZOS),
            brand / name,
            quality=92,
        )


def export_tray_icons(source: Path, icons_dir: Path) -> None:
    """Pure black template glyph on fully transparent background for macOS menu bar."""
    src = Image.open(source).convert("RGBA")
    if src.size != (BRAND_CANVAS, BRAND_CANVAS):
        src = src.resize((BRAND_CANVAS, BRAND_CANVAS), Image.Resampling.LANCZOS)

    layer = fit_foreground_layer(src, BRAND_CANVAS)
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
    master = repo / "myrm-agent-frontend/public/icons/.app-icon-master-1024-macos.png"
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
        f"app/PWA squircle + brand {{128,256}} webp + tray; enclosure={ENCLOSURE_SIZE}px gutter={GUTTER}px"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
