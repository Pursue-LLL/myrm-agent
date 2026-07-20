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


def _make_upload(content: bytes) -> MagicMock:
    """Create a mock UploadFile that streams content in chunks."""
    stream = io.BytesIO(content)
    upload = MagicMock()
    upload.filename = "test.txt"

    async def mock_read(size: int = -1) -> bytes:
        return stream.read(size)

    upload.read = mock_read
    return upload
