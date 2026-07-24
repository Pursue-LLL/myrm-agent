"""DB integration tests for clarification answered persistence."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.services.agent.stream_session.stream_finalize import (
    _mark_pending_clarification_answered,
)
from app.services.chat.chat_service import ChatService


def _make_msg(
    chat_id: str,
    role: str,
    content: str,
    *,
    msg_id: str,
    created_at: datetime,
    extra_data: dict[str, object] | None = None,
) -> MessageDTO:
    return MessageDTO(
        id=msg_id,
        chat_id=chat_id,
        role=role,
        content=content,
        sent_at=created_at,
        sent_timezone="UTC",
        created_at=created_at,
        extra_data=extra_data,
    )


@pytest.fixture
async def clarify_patch_chat(db_session: AsyncSession) -> str:
    chat_id = "clarify-patch-db"
    db_session.add(Chat(id=chat_id, title="Clarify Patch Chat", source="web"))
    await db_session.flush()

    base = datetime(2025, 6, 1, 10, 0, 0)
    clarify_extra: dict[str, object] = {
        "clarification": {
            "answered": False,
            "title": "Destination",
            "isResumeMode": True,
        }
    }
    msgs = [
        _make_msg(chat_id, "user", "Plan a trip", msg_id="u1", created_at=base),
        _make_msg(
            chat_id,
            "assistant",
            "Which destination?",
            msg_id="a1-clarify",
            created_at=base + timedelta(seconds=1),
            extra_data=clarify_extra,
        ),
        _make_msg(
            chat_id,
            "assistant",
            "Regenerated draft",
            msg_id="a2-followup",
            created_at=base + timedelta(seconds=2),
        ),
    ]
    await ChatRepository.add_messages(db_session, msgs)
    await db_session.commit()
    return chat_id


@pytest.mark.asyncio
async def test_mark_pending_clarification_answered_persists_to_sqlite(
    clarify_patch_chat: str,
) -> None:
    await _mark_pending_clarification_answered(clarify_patch_chat)

    messages = await ChatService.get_all_messages(clarify_patch_chat)
    clarify_message = next(message for message in messages if message.id == "a1-clarify")
    extra_data = clarify_message.extra_data
    assert isinstance(extra_data, dict)
    clarification = extra_data.get("clarification")
    assert isinstance(clarification, dict)
    assert clarification.get("answered") is True
    assert clarification.get("title") == "Destination"
