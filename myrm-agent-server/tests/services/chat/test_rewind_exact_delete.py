"""A rewind deletes the rows its first step found, the ones its file revert covered, and no others.

The first step reads the anchor and every row after it, inactive siblings included; the files are reverted for the
active ones among them and the last step deletes exactly those rows. A row another writer adds in between (an IM reply,
the note of a settled background task) was never reverted, so deleting it would lose it without a trace.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Chat, Message
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.uow import UnitOfWork
from app.services.chat.chat_service import ChatService

pytestmark = pytest.mark.usefixtures("db_session", "rewind_collaborators")

CHAT_ID = "chat-rewind-exact"
FIRST_ROW_AT = datetime(2025, 1, 1, 12, 0, 0)
REVERT_FILES = "app.services.chat.chat_turn.revert_files_for_messages"


def _message(
    message_id: str, role: str, content: str, at_second: int, *, sibling_group: str | None = None, active: bool = True
) -> MessageDTO:
    created_at = FIRST_ROW_AT + timedelta(seconds=at_second)
    return MessageDTO(
        id=message_id,
        chat_id=CHAT_ID,
        role=role,
        content=content,
        sent_at=created_at,
        sent_timezone="UTC",
        created_at=created_at,
        sibling_group_id=sibling_group,
        is_active=active,
    )


async def _seed(db: AsyncSession, *messages: MessageDTO) -> None:
    db.add(Chat(id=CHAT_ID, title="Test", source="web"))
    await db.flush()
    await ChatRepository.add_messages(db, list(messages))
    await db.commit()


async def _stored_ids(db: AsyncSession) -> list[str]:
    """Every row of the chat, inactive ones included."""
    return sorted((await db.execute(select(Message.id).where(Message.chat_id == CHAT_ID))).scalars().all())


@pytest.mark.asyncio
async def test_a_row_written_while_the_files_are_reverted_is_neither_reverted_nor_deleted(db_session: AsyncSession) -> None:
    await _seed(
        db_session,
        _message("u1", "user", "Q1", 0),
        _message("a1", "assistant", "A1", 1),
        _message("u2", "user", "Q2", 2),
        _message("a2", "assistant", "A2", 3),
    )
    reverted: list[list[str]] = []

    async def revert_while_an_im_reply_arrives(chat_id: str, message_ids: list[str]) -> dict[str, list[str]]:
        reverted.append(list(message_ids))
        async with UnitOfWork() as uow:
            await uow.chat_repo.add_message(_message("im-reply", "assistant", "IM reply", 600))
        return {}

    with patch(REVERT_FILES, new=revert_while_an_im_reply_arrives):
        result = await ChatService.rewind_to_message(CHAT_ID, "u2", revert_files=True)

    assert result.success is True
    assert result.deleted_count == 2
    assert reverted == [["u2", "a2"]]
    assert await _stored_ids(db_session) == ["a1", "im-reply", "u1"]


@pytest.mark.asyncio
async def test_the_inactive_siblings_after_the_anchor_go_with_the_rewind(db_session: AsyncSession) -> None:
    await _seed(
        db_session,
        _message("u1", "user", "Q1", 0),
        _message("a1", "assistant", "A1", 1),
        _message("u2", "user", "Q2", 2),
        _message("a2-first-try", "assistant", "A2 first try", 3, sibling_group="answers-to-u2", active=False),
        _message("a2", "assistant", "A2", 4, sibling_group="answers-to-u2"),
    )

    result = await ChatService.rewind_to_message(CHAT_ID, "u2")

    assert result.success is True
    assert result.deleted_count == 3
    assert await _stored_ids(db_session) == ["a1", "u1"]
