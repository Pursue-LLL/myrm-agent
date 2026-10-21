"""Tests for media file reader used by vision resolve injection."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.utils.media_file_reader import read_uploaded_media_file_content


@pytest.mark.asyncio
async def test_read_uploaded_media_file_content_delegates_to_files_service() -> None:
    with patch(
        "app.core.storage.files_service.get_content",
        new=AsyncMock(return_value=b"image-bytes"),
    ) as get_content:
        result = await read_uploaded_media_file_content("file_abc")

    assert result == b"image-bytes"
    get_content.assert_awaited_once_with("file_abc")


@pytest.mark.asyncio
async def test_read_uploaded_media_file_content_returns_none_on_error() -> None:
    with patch(
        "app.core.storage.files_service.get_content",
        new=AsyncMock(side_effect=RuntimeError("missing")),
    ):
        result = await read_uploaded_media_file_content("missing")

    assert result is None
