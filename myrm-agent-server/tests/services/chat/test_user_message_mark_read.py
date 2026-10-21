"""A message a person typed records their presence; a system-injected one does not."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, update

from app.database.models.chat import Chat, Message
from app.platform_utils import get_session_factory
from app.services.chat.chat_service import ChatService
from tests.support.minimal_app import build_minimal_app

build_minimal_app(preset="chats")


async def _send(chat_id: str, *, message_id: str | None = None, mark_read: bool) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="Summarise the report",
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        message_id=message_id,
        mark_read=mark_read,
    )


async def _last_read_at(chat_id: str) -> datetime | None:
    async with get_session_factory()() as db:
        return (await db.execute(select(Chat.last_read_at).where(Chat.id == chat_id))).scalar_one()


async def _message_created_at(chat_id: str) -> datetime:
    async with get_session_factory()() as db:
        stmt = select(Message.created_at).where(Message.chat_id == chat_id, Message.role == "user")
        return (await db.execute(stmt)).scalar_one()


@pytest.mark.asyncio
async def test_a_typed_message_in_a_new_chat_records_presence() -> None:
    chat_id = f"mark-read-{uuid.uuid4().hex[:8]}"

    await _send(chat_id, mark_read=True)

    last_read_at = await _last_read_at(chat_id)
    assert last_read_at is not None
    assert last_read_at >= await _message_created_at(chat_id)


@pytest.mark.asyncio
async def test_a_system_message_in_a_new_chat_leaves_the_chat_unread() -> None:
    chat_id = f"mark-read-{uuid.uuid4().hex[:8]}"

    await _send(chat_id, mark_read=False)

    assert await _last_read_at(chat_id) is None


@pytest.mark.asyncio
async def test_a_typed_message_moves_presence_past_an_earlier_reply() -> None:
    chat_id = f"mark-read-{uuid.uuid4().hex[:8]}"
    await _send(chat_id, mark_read=True)
    await ChatService.persist_assistant_message_safe(chat_id, "The report is ready.", timezone="UTC", request_message_id="req-1")
    async with get_session_factory()() as db:
        reply_at = (
            await db.execute(select(Message.created_at).where(Message.chat_id == chat_id, Message.role == "assistant"))
        ).scalar_one()
        await db.execute(update(Chat).where(Chat.id == chat_id).values(last_read_at=reply_at - timedelta(minutes=5)))
        await db.commit()

    await _send(chat_id, mark_read=True)

    last_read_at = await _last_read_at(chat_id)
    assert last_read_at is not None
    assert last_read_at > reply_at


@pytest.mark.asyncio
async def test_a_system_message_in_an_existing_chat_keeps_the_presence_mark() -> None:
    chat_id = f"mark-read-{uuid.uuid4().hex[:8]}"
    await _send(chat_id, mark_read=True)
    before = await _last_read_at(chat_id)

    await _send(chat_id, mark_read=False)

    assert await _last_read_at(chat_id) == before
