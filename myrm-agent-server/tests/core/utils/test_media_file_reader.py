"""Tests for the media byte reader injected into vision resolve."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.core.utils.media_file_reader import read_media_content


@pytest.mark.asyncio
async def test_read_media_content_delegates_a_bare_id_to_files_service() -> None:
    with patch(
        "app.core.storage.files_service.get_content",
        new=AsyncMock(return_value=b"image-bytes"),
    ) as get_content:
        result = await read_media_content("file_abc")

    assert result == b"image-bytes"
    get_content.assert_awaited_once_with("file_abc")


@pytest.mark.asyncio
async def test_read_media_content_returns_none_on_error() -> None:
    with patch(
        "app.core.storage.files_service.get_content",
        new=AsyncMock(side_effect=RuntimeError("missing")),
    ):
        result = await read_media_content("missing")

    assert result is None


@pytest.mark.asyncio
async def test_read_media_content_resolves_a_media_reference_through_the_library() -> None:
    with (
        patch(
            "app.core.media.reference.read_media_reference",
            new=AsyncMock(return_value=b"generated-bytes"),
        ) as read_reference,
        patch("app.core.storage.files_service.get_content", new=AsyncMock()) as get_content,
    ):
        result = await read_media_content("media://media_abc")

    assert result == b"generated-bytes"
    read_reference.assert_awaited_once_with("media_abc")
    get_content.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [LookupError("no record"), FileNotFoundError("file gone")])
async def test_read_media_content_is_none_for_a_reference_that_holds_nothing(error: Exception) -> None:
    with patch("app.core.media.reference.read_media_reference", new=AsyncMock(side_effect=error)):
        assert await read_media_content("media://media_gone") is None
