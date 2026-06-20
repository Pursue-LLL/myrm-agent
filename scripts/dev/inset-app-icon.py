#!/usr/bin/env python3
"""Inset app icon artwork to macOS HIG safe zone (~82% content area)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

CONTENT_SCALE = 0.82
CANVAS = 512


def inset_icon(source: Path, dest: Path, scale: float = CONTENT_SCALE) -> None:
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)

    content_size = max(1, round(CANVAS * scale))
    resized = src.resize((content_size, content_size), Image.Resampling.LANCZOS)
    offset = (CANVAS - content_size) // 2

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(resized, (offset, offset), resized)
    dest.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(dest, optimize=True)


def export_png_sizes(master: Path, outputs: dict[int, Path]) -> None:
    base = Image.open(master).convert("RGBA")
    for size, path in outputs.items():
        img = base if size == CANVAS else base.resize((size, size), Image.Resampling.LANCZOS)
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(path, optimize=True)


def export_webp_from_image(img: Image.Image, dest: Path, quality: int = 86) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGBA").save(dest, format="WEBP", quality=quality, method=6)


def export_webp(master: Path, dest: Path, quality: int = 86) -> None:
    export_webp_from_image(Image.open(master), dest, quality=quality)


def main() -> int:
    repo = Path(__file__).resolve().parents[2]
    source = repo / "myrm-agent-desktop/src-tauri/icons/icon.png"
    if not source.exists():
        source = repo / "myrm-agent-frontend/public/brand/logo-icon-512.png"
    if not source.exists():
        print(f"ERROR: source icon not found: {source}", file=sys.stderr)
        return 1

    master = repo / "myrm-agent-frontend/public/brand/logo-icon-512-inset.png"
    inset_icon(source, master)

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
        if not paths:
            continue
        export_png_sizes(master, {size: paths[0]})
        for extra in paths[1:]:
            extra.write_bytes(paths[0].read_bytes())

    export_webp(master, brand / "logo-icon.webp")
    export_webp_from_image(
        Image.open(master).resize((128, 128), Image.Resampling.LANCZOS),
        brand / "logo-icon-128.webp",
    )
    export_webp_from_image(
        Image.open(master).resize((80, 80), Image.Resampling.LANCZOS),
        brand / "logo-icon-80.webp",
    )

    desktop = repo / "myrm-agent-desktop"
    subprocess.run(
        ["cargo", "tauri", "icon", str(master)],
        cwd=desktop,
        check=True,
    )

    master.unlink(missing_ok=True)
    print(f"OK: inset icon generated from {source} at scale={CONTENT_SCALE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
