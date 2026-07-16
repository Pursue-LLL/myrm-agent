"""Tests for chat share HTML renderer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.dto import ChatDTO, MessageDTO
from app.services.chat.share_renderer import render_share_html


def _make_chat(chat_id: str = "chat-1") -> ChatDTO:
    now = datetime.now(timezone.utc)
    return ChatDTO(
        id=chat_id,
        agent_id="agent-1",
        title="My Test Chat",
        first_message="Hello world",
        created_at=now,
        updated_at=now,
    )


def _make_messages() -> list[MessageDTO]:
    now = datetime.now(timezone.utc)
    return [
        MessageDTO(
            id="m1", chat_id="chat-1", role="user", content="Hello",
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
        MessageDTO(
            id="m2", chat_id="chat-1", role="assistant", content="Hi there!",
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
        MessageDTO(
            id="m3", chat_id="chat-1", role="system", content="System prompt",
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
    ]


@pytest.fixture
def mock_db():
    db = MagicMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)
    return db


async def test_render_share_html_basic(mock_db) -> None:
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=_make_messages(),
        ),
    ):
        html = await render_share_html("chat-1", mock_db)
        assert html is not None
        assert "My Test Chat" in html
        assert "Hello" in html
        assert "Hi there!" in html
        assert "System prompt" not in html
        assert "<!DOCTYPE html>" in html
        assert "og:title" in html


async def test_render_share_html_chat_not_found(mock_db) -> None:
    with patch(
        "app.services.chat.share_renderer.ChatService.get_chat_metadata",
        new_callable=AsyncMock,
        return_value=None,
    ):
        html = await render_share_html("nonexistent", mock_db)
        assert html is None


async def test_render_share_html_escapes_xss(mock_db) -> None:
    now = datetime.now(timezone.utc)
    xss_messages = [
        MessageDTO(
            id="m1", chat_id="chat-1", role="user",
            content='<script>alert("xss")</script>',
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
    ]
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=_make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=xss_messages,
        ),
    ):
        html = await render_share_html("chat-1", mock_db)
        assert html is not None
        assert "<script>" not in html
        assert "&lt;script&gt;" in html
