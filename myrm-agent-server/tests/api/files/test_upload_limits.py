"""Tests for upload.py streaming upload and file-count limits (F7).

Covers:
- _stream_to_bytes streaming reader with size cap
- _MAX_FILES file count validation
- _MAX_FILE_BYTES per-file size validation
- _get_file_extension helper
- _infer_content_type helper
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.files.upload import (
    _MAX_FILE_BYTES,
    _MAX_FILES,
    _STREAM_CHUNK_SIZE,
    _get_file_extension,
    _infer_content_type,
    _stream_to_bytes,
)


class TestStreamToBytes:
    """Tests for _stream_to_bytes streaming reader."""

    @pytest.mark.asyncio
    async def test_reads_small_file_completely(self) -> None:
        content = b"hello world"
        upload = _make_upload(content)
        result = await _stream_to_bytes(upload, _MAX_FILE_BYTES)
        assert result == content

    @pytest.mark.asyncio
    async def test_reads_exact_limit(self) -> None:
        content = b"x" * _MAX_FILE_BYTES
        upload = _make_upload(content)
        result = await _stream_to_bytes(upload, _MAX_FILE_BYTES)
        assert len(result) == _MAX_FILE_BYTES

    @pytest.mark.asyncio
    async def test_rejects_oversized_file(self) -> None:
        content = b"x" * (_MAX_FILE_BYTES + 1)
        upload = _make_upload(content)
        with pytest.raises(Exception, match="exceeds.*50MB"):
            await _stream_to_bytes(upload, _MAX_FILE_BYTES)

    @pytest.mark.asyncio
    async def test_reads_empty_file(self) -> None:
        upload = _make_upload(b"")
        result = await _stream_to_bytes(upload, _MAX_FILE_BYTES)
        assert result == b""

    @pytest.mark.asyncio
    async def test_reads_in_chunks(self) -> None:
        """Verify data is read in _STREAM_CHUNK_SIZE chunks."""
        content = b"a" * (_STREAM_CHUNK_SIZE * 3 + 100)
        read_calls: list[int] = []

        async def tracked_read(size: int) -> bytes:
            read_calls.append(size)
            start = sum(read_calls[:-1])
            end = start + size
            chunk = content[start:end]
            return chunk

        upload = MagicMock()
        upload.filename = "test.txt"
        upload.read = tracked_read

        result = await _stream_to_bytes(upload, _MAX_FILE_BYTES)
        assert result == content
        assert all(s == _STREAM_CHUNK_SIZE for s in read_calls[:-1])

    @pytest.mark.asyncio
    async def test_custom_max_bytes(self) -> None:
        limit = 1024
        content = b"x" * (limit + 1)
        upload = _make_upload(content)
        with pytest.raises(HTTPException):
            await _stream_to_bytes(upload, limit)


class TestFileCountLimit:
    """Tests for _MAX_FILES constant."""

    def test_max_files_is_20(self) -> None:
        assert _MAX_FILES == 20

    def test_max_file_bytes_is_50mb(self) -> None:
        assert _MAX_FILE_BYTES == 50 * 1024 * 1024

    def test_stream_chunk_size_is_64kb(self) -> None:
        assert _STREAM_CHUNK_SIZE == 64 * 1024


class TestGetFileExtension:
    """Tests for _get_file_extension helper."""

    def test_normal_extension(self) -> None:
        assert _get_file_extension("report.pdf") == ".pdf"

    def test_uppercase_extension(self) -> None:
        assert _get_file_extension("IMAGE.PNG") == ".png"

    def test_no_extension(self) -> None:
        assert _get_file_extension("Makefile") == ""

    def test_multiple_dots(self) -> None:
        assert _get_file_extension("archive.tar.gz") == ".gz"

    def test_dot_only(self) -> None:
        assert _get_file_extension(".gitignore") == ".gitignore"


class TestInferContentType:
    """Tests for _infer_content_type helper."""

    def test_uses_client_type_when_valid(self) -> None:
        assert _infer_content_type("doc.pdf", "application/pdf") == "application/pdf"

    def test_infers_from_extension_when_octet_stream(self) -> None:
        result = _infer_content_type("doc.pdf", "application/octet-stream")
        assert result == "application/pdf"

    def test_infers_from_extension_when_none(self) -> None:
        result = _infer_content_type("image.png", None)
        assert result == "image/png"

    def test_returns_none_for_unknown(self) -> None:
        result = _infer_content_type("file.xyz123", None)
        assert result is None


class TestCompressImage:
    """Tests for _compress_image send-time compression (GIF protection + responsive)."""

    @pytest.mark.asyncio
    async def test_small_image_passes_through_unchanged(self) -> None:
        """Small images bypass compression entirely (zero-loss fast path)."""
        from PIL import Image

        buf = io.BytesIO()
        Image.new("RGB", (640, 480), color=(100, 150, 200)).save(buf, format="PNG")
        content = buf.getvalue()

        from app.api.files.upload import _compress_image

        result = await _compress_image(content, "small.png")
        assert result == content

    @pytest.mark.asyncio
    async def test_oversized_image_compressed(self) -> None:
        """Oversized images are downsampled to 2048px and shrunk."""
        from PIL import Image

        img = Image.new("RGB", (6000, 4000), color=(100, 150, 200))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        content = buf.getvalue()

        from app.api.files.upload import _compress_image

        result = await _compress_image(content, "large.jpg")
        assert result is not content
        assert len(result) < len(content)
        out = Image.open(io.BytesIO(result))
        assert max(out.size) <= 2048

    @pytest.mark.asyncio
    async def test_animated_gif_preserved(self) -> None:
        """Animated GIFs keep their animation frames — never flattened to a static image."""
        from PIL import Image

        frames = [
            Image.new("RGB", (64, 64), color=(255, 0, 0)),
            Image.new("RGB", (64, 64), color=(0, 255, 0)),
            Image.new("RGB", (64, 64), color=(0, 0, 255)),
        ]
        buf = io.BytesIO()
        frames[0].save(buf, format="GIF", save_all=True, append_images=frames[1:], duration=100, loop=0)
        content = buf.getvalue()

        from app.api.files.upload import _compress_image

        result = await _compress_image(content, "anim.gif")
        assert result == content
        out = Image.open(io.BytesIO(result))
        assert getattr(out, "n_frames", 1) == 3


def _make_upload(content: bytes) -> MagicMock:
    """Create a mock UploadFile that streams content in chunks."""
    stream = io.BytesIO(content)
    upload = MagicMock()
    upload.filename = "test.txt"

    async def mock_read(size: int = -1) -> bytes:
        return stream.read(size)

    upload.read = mock_read
    return upload
