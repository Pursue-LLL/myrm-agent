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
        MessageDTO(
            id="m2", chat_id="chat-1", role="assistant",
            content='<img onerror=alert(1) src=x> and **bold**',
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
        assert "<img" not in html
        assert "<strong>bold</strong>" in html


async def test_render_message_markdown(mock_db) -> None:
    """Assistant messages are rendered as Markdown; user messages are plain text."""
    now = datetime.now(timezone.utc)
    messages = [
        MessageDTO(
            id="m1", chat_id="chat-1", role="user",
            content="**not bold** `not code`",
            sent_at=now, sent_timezone="UTC", created_at=now,
        ),
        MessageDTO(
            id="m2", chat_id="chat-1", role="assistant",
            content="**bold** and `code`\n\n```python\nprint(1)\n```\n\n| A | B |\n|---|---|\n| 1 | 2 |",
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
            return_value=messages,
        ),
    ):
        html = await render_share_html("chat-1", mock_db)
        assert html is not None
        # Assistant: Markdown rendered
        assert "<strong>bold</strong>" in html
        assert "<code>code</code>" in html
        assert '<code class="language-python">' in html
        assert "<table>" in html
        # User: plain text, no Markdown rendering
        assert "**not bold**" in html
        assert "<strong>not bold</strong>" not in html


async def test_render_html_includes_dark_mode(mock_db) -> None:
    """Generated HTML includes dark mode CSS."""
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
        assert "prefers-color-scheme:dark" in html
        assert "background:#111827" in html


async def test_render_share_html_with_agent_model_selection() -> None:
    """Agent with model_selection renders model name in identity card."""
    from app.database.models.agent import Agent

    mock_agent = MagicMock(spec=Agent)
    mock_agent.name = "Code Developer"
    mock_agent.description = "Focused coding assistant"
    mock_agent.model_selection = {"model": "gpt-4o", "provider": "openai"}

    db = MagicMock()
    agent_result = MagicMock()
    agent_result.scalars.return_value.first.return_value = mock_agent
    db.execute = AsyncMock(return_value=agent_result)

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
        html = await render_share_html("chat-1", db)
        assert html is not None
        assert "Code Developer" in html
        assert "gpt-4o" in html
