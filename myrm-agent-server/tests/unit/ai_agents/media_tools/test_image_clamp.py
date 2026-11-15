"""Unit tests for image_clamp and for the single clamp every resolved image passes through."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.media_inputs import resolve_media_inputs
from PIL import Image

from app.ai_agents.media_tools.image_clamp import (
    clamp_image_payload,
)
from app.ai_agents.media_tools.input_policy import build_media_input_policy


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
async def test_a_media_library_reference_is_clamped_on_the_way_out() -> None:
    oversized = _create_test_image((2500, 1000), mode="RGB", fmt="JPEG")

    with patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(return_value=oversized)):
        (resolved,) = await resolve_media_inputs(
            ["media://media_big"], "image", build_media_input_policy(), field_name="image_url"
        )

    with Image.open(io.BytesIO(resolved)) as img:
        assert max(img.width, img.height) <= 2048


@pytest.mark.asyncio
async def test_a_workspace_file_reference_is_clamped_on_the_way_out(tmp_path: Path) -> None:
    (tmp_path / "large_photo.jpg").write_bytes(_create_test_image((3200, 1600), mode="RGB", fmt="JPEG"))

    (resolved,) = await resolve_media_inputs(
        ["large_photo.jpg"], "image", build_media_input_policy([str(tmp_path)]), field_name="reference_images"
    )

    with Image.open(io.BytesIO(resolved)) as img:
        assert max(img.width, img.height) <= 2048
