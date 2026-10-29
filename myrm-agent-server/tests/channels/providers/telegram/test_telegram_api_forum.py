"""Tests for providers/telegram/api_forum.py — Forum Topic methods."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.channels.providers.telegram.api_core import TelegramApiError
from tests.channels.providers.telegram.telegram_client_mocks import _error_response, _mock_client, _ok_response


class TestForumTopicApi:
    """Test the 5 Forum Topic API methods on TelegramClient."""

    @pytest.mark.asyncio
    async def test_create_forum_topic(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_thread_id": 42, "name": "Test Topic"}))
        result = await client.create_forum_topic(-100123, "Test Topic", icon_color=0x6FB9F0)
        assert result["message_thread_id"] == 42
        assert result["name"] == "Test Topic"

    @pytest.mark.asyncio
    async def test_create_forum_topic_with_emoji(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response({"message_thread_id": 43, "name": "Dev"}))
        result = await client.create_forum_topic(-100123, "Dev", icon_custom_emoji_id="5368324170671202286")
        assert result["message_thread_id"] == 43

    @pytest.mark.asyncio
    async def test_edit_forum_topic(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response(True))
        result = await client.edit_forum_topic(-100123, 42, name="Renamed")
        assert result is True

    @pytest.mark.asyncio
    async def test_edit_forum_topic_icon_only(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response(True))
        result = await client.edit_forum_topic(-100123, 42, icon_custom_emoji_id="5368324170671202286")
        assert result is True

    @pytest.mark.asyncio
    async def test_close_forum_topic(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.close_forum_topic(-100123, 42) is True

    @pytest.mark.asyncio
    async def test_reopen_forum_topic(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.reopen_forum_topic(-100123, 42) is True

    @pytest.mark.asyncio
    async def test_delete_forum_topic(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_ok_response(True))
        assert await client.delete_forum_topic(-100123, 42) is True

    @pytest.mark.asyncio
    async def test_create_forum_topic_permission_error(self) -> None:
        client, http = _mock_client()
        http.post = AsyncMock(return_value=_error_response(403, "Forbidden: not enough rights"))
        with pytest.raises(TelegramApiError, match="not enough rights"):
            await client.create_forum_topic(-100123, "Forbidden Topic")
