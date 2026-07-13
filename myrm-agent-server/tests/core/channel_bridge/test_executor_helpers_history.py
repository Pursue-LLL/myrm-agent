"""Tests for channel executor history helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.channel_bridge.executor_helpers.history import (
    load_history_without_persist,
    persist_and_load_history,
    persist_assistant_message,
)
from app.services.chat.chat_helpers import ChannelHistoryEntry


@pytest.mark.asyncio
async def test_persist_and_load_history_commits_chat() -> None:
    created = datetime(2026, 7, 13, tzinfo=timezone.utc)
    history_entry = ChannelHistoryEntry(role="human", content="Hi", created_at=created)
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "app.database.connection.get_session",
        ) as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_or_create_channel_chat",
            new_callable=AsyncMock,
        ) as mock_get_chat,
        patch(
            "app.services.chat.chat_service.ChatService.append_message",
            new_callable=AsyncMock,
        ) as mock_append,
        patch(
            "app.services.chat.chat_service.ChatService.load_channel_history",
            new_callable=AsyncMock,
            return_value=[history_entry],
        ),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False
        mock_chat = MagicMock()
        mock_chat.id = "chat-1"
        mock_get_chat.return_value = mock_chat

        chat_id, history = await persist_and_load_history(
            "telegram:peer",
            "telegram",
            "Hello",
            created,
            "UTC",
        )

    assert chat_id == "chat-1"
    assert history == [history_entry]
    mock_append.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_history_without_persist_returns_empty_when_missing() -> None:
    mock_session = AsyncMock()

    with (
        patch(
            "app.database.connection.get_session",
        ) as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_channel_chat_by_key",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False

        chat_id, history = await load_history_without_persist("missing:key")

    assert chat_id == ""
    assert history == []


@pytest.mark.asyncio
async def test_load_history_without_persist_returns_history() -> None:
    created = datetime(2026, 7, 13, tzinfo=timezone.utc)
    history_entry = ChannelHistoryEntry(role="human", content="Hi", created_at=created)
    mock_session = AsyncMock()
    mock_chat = MagicMock()
    mock_chat.id = "chat-9"

    with (
        patch("app.database.connection.get_session") as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_channel_chat_by_key",
            new_callable=AsyncMock,
            return_value=mock_chat,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_channel_history",
            new_callable=AsyncMock,
            return_value=[history_entry],
        ),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False

        chat_id, history = await load_history_without_persist("telegram:peer")

    assert chat_id == "chat-9"
    assert history == [history_entry]


@pytest.mark.asyncio
async def test_persist_assistant_message_appends() -> None:
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "app.database.connection.get_session",
        ) as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.append_message",
            new_callable=AsyncMock,
        ) as mock_append,
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False

        await persist_assistant_message("chat-1", "Reply", timezone="Asia/Shanghai")

    mock_append.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
