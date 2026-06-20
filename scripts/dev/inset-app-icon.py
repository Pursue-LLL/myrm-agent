#!/usr/bin/env python3
"""Generate macOS Dock app icons: scale source artwork to Apple 824/1024 safe zone."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image

# Apple Developer Forums #670578: 824x824 artwork on 1024 canvas → halved for 512 master.
CANVAS = 512
FACE_SIZE = 412
GUTTER = 50


def make_macos_icon(source: Path) -> Image.Image:
    src = Image.open(source).convert("RGBA")
    if src.size != (CANVAS, CANVAS):
        src = src.resize((CANVAS, CANVAS), Image.Resampling.LANCZOS)

    bbox = src.getbbox() or (0, 0, CANVAS, CANVAS)
    art = src.crop(bbox)
    art = art.resize((FACE_SIZE, FACE_SIZE), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    canvas.paste(art, (GUTTER, GUTTER), art)
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
    icon = make_macos_icon(source)
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
    git_src = repo / "myrm-agent-frontend/public/brand/.logo-icon-source-512.png"
    git_src.unlink(missing_ok=True)
    print(f"OK: macOS icon from {source} face={FACE_SIZE}px gutter={GUTTER}px (no shadow/mask)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
