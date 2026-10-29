"""The chat list's preview and title come from what a person said, never from the system's note about a settled task.

Read from the real chat table: the preview columns are what the sidebar renders.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import update

from app.database import connection
from app.database.models import Chat
from app.database.models.chat import WAKEUP_NOTICE_DEGRADED, WAKEUP_NOTICE_FOLLOWUP, WAKEUP_NOTICE_KEY
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.uow import UnitOfWork
from app.services.chat.chat_service import ChatService
from app.services.chat.chat_turn import _ChatTurnMixin

pytestmark = pytest.mark.usefixtures("setup_test_database")

_NOTICE_XML = "<system_notification type='adaptive_wakeup_followup'>job done</system_notification>"


async def _append(chat_id: str, content: str, extra_data: dict[str, object] | None = None) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content=content,
        sent_at=datetime.now(timezone.utc),
        sent_timezone="UTC",
        extra_data=extra_data,
    )


async def _chat(chat_id: str) -> Chat:
    async with connection.get_session() as db:
        chat = await db.get(Chat, chat_id)
        assert chat is not None
        db.expunge(chat)
        return chat


@pytest.mark.parametrize("kind", [WAKEUP_NOTICE_FOLLOWUP, WAKEUP_NOTICE_DEGRADED])
async def test_a_settlement_note_leaves_the_preview_and_title_of_the_chat_alone(kind: str) -> None:
    chat_id = str(uuid.uuid4())
    await _append(chat_id, "what the person typed")
    before = await _chat(chat_id)

    await _append(chat_id, _NOTICE_XML, {WAKEUP_NOTICE_KEY: kind})

    after = await _chat(chat_id)
    assert after.last_message == "what the person typed"
    assert after.first_message == before.first_message
    assert after.title == before.title


async def test_a_settlement_note_still_counts_as_activity_of_the_chat() -> None:
    chat_id = str(uuid.uuid4())
    await _append(chat_id, "what the person typed")
    long_ago = datetime(2026, 1, 1, tzinfo=timezone.utc)
    async with connection.get_session() as db:
        await db.execute(update(Chat).where(Chat.id == chat_id).values(updated_at=long_ago))
        await db.commit()

    await _append(chat_id, _NOTICE_XML, {WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_DEGRADED})

    after = await _chat(chat_id)
    assert after.updated_at.replace(tzinfo=timezone.utc) > long_ago + timedelta(days=30)


async def test_a_settlement_note_never_becomes_the_title_of_a_chat_without_a_first_message() -> None:
    chat_id = str(uuid.uuid4())
    async with connection.get_session() as db:
        db.add(Chat(id=chat_id, title="", first_message=None))
        await db.commit()

    await _append(chat_id, _NOTICE_XML, {WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_FOLLOWUP})

    after = await _chat(chat_id)
    assert not after.first_message
    assert "system_notification" not in (after.title or "")


async def test_what_a_person_types_after_a_settlement_note_is_the_preview_again() -> None:
    chat_id = str(uuid.uuid4())
    await _append(chat_id, "what the person typed")
    await _append(chat_id, _NOTICE_XML, {WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_DEGRADED})

    await _append(chat_id, "and then this")

    assert (await _chat(chat_id)).last_message == "and then this"


async def test_the_preview_recomputed_after_an_undo_is_never_a_settlement_note() -> None:
    chat_id = str(uuid.uuid4())
    await _append(chat_id, "what the person typed")
    await _append(chat_id, _NOTICE_XML, {WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_DEGRADED})

    async with UnitOfWork(write=True) as uow:
        await _ChatTurnMixin._refresh_last_message(uow, chat_id)
        await uow.commit()

    assert (await _chat(chat_id)).last_message == "what the person typed"


async def test_the_newest_row_of_a_chat_is_still_the_note_unless_the_conversation_is_asked_for() -> None:
    chat_id = str(uuid.uuid4())
    await _append(chat_id, "what the person typed")
    await _append(chat_id, _NOTICE_XML, {WAKEUP_NOTICE_KEY: WAKEUP_NOTICE_DEGRADED})

    async with connection.get_session() as db:
        newest = await ChatRepository.get_latest_message(db, chat_id)
        newest_said = await ChatRepository.get_latest_message(db, chat_id, conversation_only=True)

    assert newest is not None and newest.content == _NOTICE_XML
    assert newest_said is not None and newest_said.content == "what the person typed"
