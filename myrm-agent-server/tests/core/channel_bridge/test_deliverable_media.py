"""Unit tests for oversized deliverable media handling."""

from __future__ import annotations

from pathlib import Path

from app.core.channel_bridge.agent_executor.deliverable.media import (
    MAX_CHANNEL_ATTACHMENT_BYTES,
    compress_oversized_image,
    format_human_size,
    is_compressible_image,
)


def test_format_human_size() -> None:
    assert format_human_size(MAX_CHANNEL_ATTACHMENT_BYTES) == "5.0 MB"
    assert format_human_size(int(8.25 * 1024 * 1024)) == "8.2 MB"
    assert format_human_size(508) == "508 B"
    assert format_human_size(128 * 1024) == "128 KB"


def test_is_compressible_image() -> None:
    assert is_compressible_image("chart.PNG")
    assert is_compressible_image("photo.jpg")
    assert is_compressible_image("pic.webp")
    assert not is_compressible_image("anim.gif")
    assert not is_compressible_image("report.pdf")
    assert not is_compressible_image("")


def test_compress_jpeg_under_cap(tmp_path: Path) -> None:
    from PIL import Image

    src = tmp_path / "photo.jpg"
    Image.new("RGB", (1600, 1600), (200, 100, 50)).save(src, format="JPEG", quality=95)

    result = compress_oversized_image(src, max_bytes=20_000)
    assert result is not None
    try:
        assert result.exists()
        assert result.stat().st_size <= 20_000
        assert result.suffix == ".jpg"
    finally:
        result.unlink(missing_ok=True)


def test_compress_png_preserves_transparency(tmp_path: Path) -> None:
    from PIL import Image

    src = tmp_path / "logo.png"
    img = Image.new("RGBA", (800, 800), (10, 20, 30, 128))
    img.save(src, format="PNG")

    result = compress_oversized_image(src, max_bytes=50_000)
    assert result is not None
    try:
        assert result.suffix == ".png"
        with Image.open(result) as out:
            assert out.mode in {"RGBA", "LA"}
    finally:
        result.unlink(missing_ok=True)


def test_compress_png_alpha_pixels_kept(tmp_path: Path) -> None:
    from PIL import Image

    src = tmp_path / "alpha.png"
    img = Image.new("RGBA", (300, 300), (255, 0, 0, 0))
    img.save(src, format="PNG")

    result = compress_oversized_image(src, max_bytes=50_000)
    assert result is not None
    try:
        with Image.open(result) as out:
            assert out.mode in {"RGBA", "LA"}
            assert out.getpixel((0, 0))[3] == 0
    finally:
        result.unlink(missing_ok=True)


def test_compress_returns_none_for_unsupported(tmp_path: Path) -> None:
    src = tmp_path / "doc.pdf"
    src.write_bytes(b"%PDF-1.4")
    assert compress_oversized_image(src, max_bytes=1000) is None


def test_compress_returns_none_for_unreadable(tmp_path: Path) -> None:
    src = tmp_path / "broken.jpg"
    src.write_bytes(b"not an image")
    assert compress_oversized_image(src, max_bytes=1000) is None


def test_compress_returns_none_when_cap_too_small(tmp_path: Path) -> None:
    from PIL import Image

    src = tmp_path / "tiny.png"
    Image.new("RGB", (8, 8), (1, 1, 1)).save(src, format="PNG")
    assert compress_oversized_image(src, max_bytes=1) is None


def test_compress_webp_rgba_flattened_to_white(tmp_path: Path) -> None:
    """Quality-mode image (WEBP) with transparency is flattened onto white."""
    from PIL import Image

    src = tmp_path / "overlay.webp"
    Image.new("RGBA", (400, 400), (0, 0, 0, 0)).save(src, format="WEBP")

    result = compress_oversized_image(src, max_bytes=50_000)
    assert result is not None
    try:
        with Image.open(result) as out:
            assert out.mode == "RGB"
            # Original fully transparent → flattened onto white → pixel is white.
            assert out.getpixel((0, 0)) == (255, 255, 255)
    finally:
        result.unlink(missing_ok=True)


def test_compress_jpeg_greyscale_converted(tmp_path: Path) -> None:
    """Greyscale (L) JPEG is re-encoded as RGB JPEG."""
    from PIL import Image

    src = tmp_path / "gray.jpg"
    Image.new("L", (300, 300), 128).save(src, format="JPEG", quality=95)

    result = compress_oversized_image(src, max_bytes=30_000)
    assert result is not None
    try:
        with Image.open(result) as out:
            assert out.mode == "RGB"
            assert out.format == "JPEG"
    finally:
        result.unlink(missing_ok=True)


def test_compress_png_palette_converted(tmp_path: Path) -> None:
    """Palette (P) PNG is expanded to RGBA before re-encoding."""
    from PIL import Image

    src = tmp_path / "palette.png"
    rgb = Image.new("RGB", (200, 200), (30, 60, 90))
    rgb.convert("P", palette=Image.ADAPTIVE).save(src, format="PNG")

    result = compress_oversized_image(src, max_bytes=40_000)
    assert result is not None
    try:
        with Image.open(result) as out:
            assert out.mode in {"RGBA", "LA"}
    finally:
        result.unlink(missing_ok=True)
