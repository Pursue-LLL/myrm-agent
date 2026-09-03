"""Unit tests for image_clamp module and media tools input resilience."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from PIL import Image

from app.ai_agents.media_tools.image_clamp import (
    clamp_image_payload,
)


def _create_test_image(
    size: tuple[int, int],
    mode: str = "RGB",
    color: tuple[int, ...] = (255, 0, 0),
    fmt: str = "JPEG",
    exif_orientation: int | None = None,
) -> bytes:
    """Helper to generate in-memory test images."""
    img = Image.new(mode, size, color)
    buf = io.BytesIO()
    if exif_orientation is not None:
        exif = img.getexif()
        exif[0x0112] = exif_orientation
        img.save(buf, format=fmt, exif=exif)
    else:
        img.save(buf, format=fmt)
    return buf.getvalue()


def test_clamp_empty_bytes() -> None:
    data, mime, length = clamp_image_payload(b"")
    assert data == b""
    assert mime == "image/jpeg"
    assert length == 0


def test_clamp_corrupted_bytes_graceful_degradation() -> None:
    corrupted = b"not_an_image_binary_data_123456"
    data, mime, length = clamp_image_payload(corrupted)
    assert data == corrupted
    assert mime == "image/jpeg"
    assert length == len(corrupted)


def test_clamp_lossless_bypass() -> None:
    # 500x500 RGB JPEG with no EXIF: should bypass without re-encoding
    raw = _create_test_image((500, 500), mode="RGB", fmt="JPEG")
    clamped, mime, length = clamp_image_payload(raw, content_type="image/jpeg")
    assert clamped == raw
    assert mime == "image/jpeg"
    assert length == len(raw)


def test_clamp_downsamples_oversized_dimension() -> None:
    # 3000 x 1500 image should be resized down to max_dimension = 2048
    raw = _create_test_image((3000, 1500), mode="RGB", fmt="JPEG")
    clamped, mime, length = clamp_image_payload(raw, max_dimension=2048)
    assert mime == "image/jpeg"
    assert length == len(clamped)

    with Image.open(io.BytesIO(clamped)) as result_img:
        assert result_img.width <= 2048
        assert result_img.height <= 2048
        # Aspect ratio should be preserved: 3000x1500 (2:1) -> 2048x1024
        assert result_img.width == 2048
        assert result_img.height == 1024


def test_clamp_composites_rgba_alpha_to_clean_rgb() -> None:
    # RGBA image with transparent pixels: saving directly as JPEG would crash
    # clamp_image_payload should blend onto white background without error
    raw_rgba = _create_test_image(
        (400, 400),
        mode="RGBA",
        color=(255, 0, 0, 128),
        fmt="PNG",
    )
    clamped, mime, length = clamp_image_payload(raw_rgba)
    assert mime == "image/jpeg"
    assert length == len(clamped)

    with Image.open(io.BytesIO(clamped)) as result_img:
        assert result_img.mode == "RGB"
        assert result_img.size == (400, 400)


def test_clamp_exif_orientation_baked() -> None:
    # Orientation 6 corresponds to 90 degrees CCW rotation
    # A 600x300 image with orientation=6 when transposed becomes 300x600
    raw = _create_test_image(
        (600, 300),
        mode="RGB",
        fmt="JPEG",
        exif_orientation=6,
    )
    clamped, mime, length = clamp_image_payload(raw)
    assert mime == "image/jpeg"

    with Image.open(io.BytesIO(clamped)) as result_img:
        assert result_img.size == (300, 600)


@pytest.mark.asyncio
async def test_image_agent_tool_fetch_uses_clamp() -> None:
    from app.ai_agents.media_tools.image_agent_tool import _fetch_image_bytes

    oversized_raw = _create_test_image((2500, 1000), mode="RGB", fmt="JPEG")

    mock_response = AsyncMock()
    mock_response.content = oversized_raw
    mock_response.headers = {"content-type": "image/jpeg"}
    mock_response.raise_for_status = lambda: None

    with patch(
        "myrm_agent_harness.core.security.http.secure_fetch.secure_get",
        return_value=mock_response,
    ):
        body, content_type, size = await _fetch_image_bytes(
            "https://example.com/oversized.jpg",
            allow_private_networks=False,
        )

    assert content_type == "image/jpeg"
    assert size == len(body)
    with Image.open(io.BytesIO(body)) as img:
        assert max(img.width, img.height) <= 2048


def test_video_agent_tool_clamp_reference_sources(tmp_path: Path) -> None:
    from app.ai_agents.media_tools.video_agent_tool import _clamp_reference_sources

    oversized_file = tmp_path / "large_photo.jpg"
    oversized_raw = _create_test_image((3200, 1600), mode="RGB", fmt="JPEG")
    oversized_file.write_bytes(oversized_raw)

    remote_url = "https://example.com/video_ref.jpg"
    sources = [str(oversized_file), remote_url]

    sanitized = _clamp_reference_sources(sources)
    assert sanitized is not None
    assert len(sanitized) == 2

    # The local oversized file was clamped to a new temp file
    clamped_path = Path(sanitized[0])
    assert clamped_path.is_file()
    assert str(clamped_path) != str(oversized_file)

    with Image.open(clamped_path) as img:
        assert max(img.width, img.height) <= 2048

    # The remote URL is untouched at ingestion (handled downstream by executor)
    assert sanitized[1] == remote_url
