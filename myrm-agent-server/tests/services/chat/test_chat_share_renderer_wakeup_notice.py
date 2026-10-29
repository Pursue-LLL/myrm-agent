"""The shared read-only page leaves out the system's notes about settled background tasks."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.dto import ChatDTO, MessageDTO
from app.database.models.chat import WAKEUP_NOTICE_KEY
from app.services.chat.share_renderer import render_share_html


async def test_the_systems_notes_about_settled_background_tasks_are_not_on_the_shared_page() -> None:
    now = datetime.now(timezone.utc)
    chat = ChatDTO(
        id="chat-1", agent_id="agent-1", title="My Test Chat", first_message="Hello world", created_at=now, updated_at=now
    )
    note = MessageDTO(
        id="wakeup_followup_t1",
        chat_id="chat-1",
        role="user",
        content="<system_notification type='adaptive_wakeup_followup'>job done</system_notification>",
        extra_data={WAKEUP_NOTICE_KEY: "followup"},
        sent_at=now,
        sent_timezone="UTC",
        created_at=now,
    )
    typed = MessageDTO(
        id="m1", chat_id="chat-1", role="user", content="what the user typed", sent_at=now, sent_timezone="UTC", created_at=now
    )
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock(**{"scalars.return_value.first.return_value": None}))
    with (
        patch("app.services.chat.share_renderer.ChatService.get_chat_metadata", new_callable=AsyncMock, return_value=chat),
        patch(
            "app.services.chat.share_renderer.ChatService.get_all_messages", new_callable=AsyncMock, return_value=[typed, note]
        ),
    ):
        html = await render_share_html("chat-1", db, lang="en")

    assert html is not None
    assert "what the user typed" in html
    assert "adaptive_wakeup_followup" not in html
    assert "system_notification" not in html
