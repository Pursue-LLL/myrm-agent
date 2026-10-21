"""Tests for wiki agent scope resolution."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.agent_scope import resolve_chat_agent_id


@pytest.mark.asyncio
async def test_resolve_chat_agent_id_returns_none_for_empty_chat_id() -> None:
    assert await resolve_chat_agent_id(None) is None
    assert await resolve_chat_agent_id("") is None


@pytest.mark.asyncio
async def test_resolve_chat_agent_id_returns_agent_from_chat_metadata() -> None:
    chat = MagicMock()
    chat.agent_id = "legal-bot"

    with patch(
        "app.services.wiki.agent_scope.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
        return_value=chat,
    ):
        assert await resolve_chat_agent_id("chat-123") == "legal-bot"


@pytest.mark.asyncio
async def test_resolve_chat_agent_id_returns_none_when_chat_missing() -> None:
    with patch(
        "app.services.wiki.agent_scope.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
        return_value=None,
    ):
        assert await resolve_chat_agent_id("missing-chat") is None
