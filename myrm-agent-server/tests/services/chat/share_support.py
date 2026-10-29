"""Builders shared by the shared-conversation page renderer tests."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.security.share.share_locale import ShareLang
from app.database.dto import ChatDTO, MessageDTO
from app.services.chat.share_renderer import render_share_html


def make_chat(chat_id: str = "chat-1", *, created_at: datetime | None = None) -> ChatDTO:
    at = created_at or datetime.now(timezone.utc)
    return ChatDTO(
        id=chat_id,
        agent_id="agent-1",
        title="My Test Chat",
        first_message="Hello world",
        created_at=at,
        updated_at=at,
    )


def make_message(
    message_id: str,
    role: str,
    content: str,
    *,
    created_at: datetime | None = None,
    extra_data: dict[str, object] | None = None,
) -> MessageDTO:
    at = created_at or datetime.now(timezone.utc)
    return MessageDTO(
        id=message_id,
        chat_id="chat-1",
        role=role,
        content=content,
        extra_data=extra_data,
        sent_at=at,
        sent_timezone="UTC",
        created_at=at,
    )


def agentless_db() -> MagicMock:
    """A session whose agent lookup finds nothing."""
    db = MagicMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result)
    return db


async def render_page(
    db: MagicMock, lang: ShareLang, *, chat: ChatDTO | None = None, messages: list[MessageDTO] | None = None
) -> str:
    """Render the shared page of *chat* (default: a two-message chat) in *lang*."""
    default_messages = [make_message("m1", "user", "Hello"), make_message("m2", "assistant", "Hi there!")]
    with (
        patch(
            "app.services.chat.share_renderer.ChatService.get_chat_metadata",
            new_callable=AsyncMock,
            return_value=chat or make_chat(),
        ),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages",
            new_callable=AsyncMock,
            return_value=default_messages if messages is None else messages,
        ),
    ):
        html = await render_share_html("chat-1", db, lang=lang)
    assert html is not None
    return html
