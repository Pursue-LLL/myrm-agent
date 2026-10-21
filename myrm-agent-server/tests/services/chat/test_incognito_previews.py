"""An incognito chat keeps no title or message preview on any write path; a regular chat keeps its own.

Every surface that lists chats (session map, statistics, inbox) reads these columns, so the guarantee has to
hold where they are written. The three public write paths run against a real schema and the raw columns are read back.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import ChatCreate, MessageCreate
from app.database.models import Chat, Message
from app.services.chat.chat_service import ChatService

CHAT_ID = "incognito-previews-1"
QUESTION = "my medical report shows a thyroid nodule, is it serious"
NO_PREVIEW = (None, None, None)


async def _previews(db: AsyncSession) -> tuple[str | None, str | None, str | None]:
    db.expire_all()
    row = (await db.execute(select(Chat.title, Chat.first_message, Chat.last_message).where(Chat.id == CHAT_ID))).one()
    return row.title, row.first_message, row.last_message


async def _message_count(db: AsyncSession) -> int:
    return (await db.execute(select(func.count()).select_from(Message).where(Message.chat_id == CHAT_ID))).scalar_one()


@pytest.mark.asyncio
@pytest.mark.parametrize("incognito", [True, False], ids=["incognito", "regular"])
async def test_a_live_turn_stores_previews_only_for_a_regular_chat(db_session: AsyncSession, incognito: bool) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=CHAT_ID,
        content=QUESTION,
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id="m-user",
        is_incognito=incognito,
    )
    await ChatService.persist_assistant_message_safe(CHAT_ID, "It is usually benign.")

    assert await _previews(db_session) == (NO_PREVIEW if incognito else (QUESTION[:50], QUESTION, "It is usually benign."))
    assert await _message_count(db_session) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("incognito", [True, False], ids=["incognito", "regular"])
async def test_saving_a_chat_stores_previews_only_for_a_regular_chat(db_session: AsyncSession, incognito: bool) -> None:
    def save(title: str) -> ChatCreate:
        question = MessageCreate(role="user", content=QUESTION, messageId="m-user", chatId=CHAT_ID)
        return ChatCreate(
            chat_id=CHAT_ID, title=title, last_message="client preview", is_incognito=incognito, messages=[question]
        )

    await ChatService.create_or_update_chat(save("First title"))
    assert await _previews(db_session) == (NO_PREVIEW if incognito else ("First title", QUESTION, QUESTION))

    await ChatService.create_or_update_chat(save("Second title"))
    assert await _previews(db_session) == (NO_PREVIEW if incognito else ("Second title", QUESTION, QUESTION))
    assert await _message_count(db_session) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("incognito", [True, False], ids=["incognito", "regular"])
async def test_renaming_a_chat_stores_the_title_only_for_a_regular_chat(db_session: AsyncSession, incognito: bool) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=CHAT_ID, content=QUESTION, sent_at=datetime.now(UTC), sent_timezone="UTC", is_incognito=incognito
    )

    await ChatService.update_chat_title(CHAT_ID, "Thyroid report")

    title, _, _ = await _previews(db_session)
    assert title == (None if incognito else "Thyroid report")
