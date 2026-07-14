"""Integration tests for undo_last_turn/retry_last_turn returning deleted_message_ids."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.models import Chat
from app.database.repositories.chat_repo import ChatRepository
from app.services.chat.chat_service import ChatService


def _make_chat(chat_id: str = "test-chat") -> Chat:
    return Chat(id=chat_id, title="Test", source="web")


def _make_msg(
    chat_id: str,
    role: str,
    content: str,
    *,
    msg_id: str,
    created_at: datetime,
) -> MessageDTO:
    return MessageDTO(
        id=msg_id,
        chat_id=chat_id,
        role=role,
        content=content,
        sent_at=created_at,
        sent_timezone="UTC",
        created_at=created_at,
    )


async def _seed(db: AsyncSession, chat_id: str = "chat-1") -> list[MessageDTO]:
    db.add(_make_chat(chat_id))
    await db.flush()
    base = datetime(2025, 1, 1, 12, 0, 0)
    msgs = [
        _make_msg(chat_id, "user", "Q1", msg_id="u1", created_at=base),
        _make_msg(chat_id, "assistant", "A1", msg_id="a1", created_at=base + timedelta(seconds=1)),
        _make_msg(chat_id, "user", "Q2", msg_id="u2", created_at=base + timedelta(seconds=2)),
        _make_msg(chat_id, "assistant", "A2", msg_id="a2", created_at=base + timedelta(seconds=3)),
    ]
    await ChatRepository.add_messages(db, msgs)
    await db.commit()
    return msgs


class TestRetryLastTurnIds:
    async def test_returns_deleted_ids(self, db_session: AsyncSession) -> None:
        await _seed(db_session, "chat-retry")

        result = await ChatService.retry_last_turn("chat-retry")

        assert result.success is True
        assert result.query == "Q2"
        assert result.deleted_count == 1
        assert result.deleted_message_ids == ["a2"]

    async def test_no_messages_returns_empty_ids(self, db_session: AsyncSession) -> None:
        db_session.add(_make_chat("empty"))
        await db_session.flush()
        await db_session.commit()

        result = await ChatService.retry_last_turn("empty")

        assert result.success is False
        assert result.deleted_message_ids == []


class TestUndoLastTurnIds:
    async def test_returns_deleted_ids_including_anchor(self, db_session: AsyncSession) -> None:
        await _seed(db_session, "chat-undo")

        result = await ChatService.undo_last_turn("chat-undo")

        assert result.success is True
        assert result.deleted_count == 2
        assert set(result.deleted_message_ids) == {"u2", "a2"}

    async def test_no_user_message_returns_empty(self, db_session: AsyncSession) -> None:
        chat_id = "undo-empty"
        db_session.add(_make_chat(chat_id))
        await db_session.flush()
        await db_session.commit()

        result = await ChatService.undo_last_turn(chat_id)

        assert result.success is True
        assert result.deleted_count == 0
        assert result.deleted_message_ids == []

    async def test_nonexistent_chat_returns_failure(self, db_session: AsyncSession) -> None:
        result = await ChatService.undo_last_turn("no-such-chat")

        assert result.success is False
        assert result.deleted_message_ids == []

    async def test_deleted_ids_match_removed_messages(self, db_session: AsyncSession) -> None:
        """Verify that the returned IDs correspond to messages actually removed from DB."""
        chat_id = "chat-verify"
        await _seed(db_session, chat_id)

        result = await ChatService.undo_last_turn(chat_id)

        remaining = await ChatRepository.get_all_messages(db_session, chat_id)
        remaining_ids = {m.id for m in remaining}
        for deleted_id in result.deleted_message_ids:
            assert deleted_id not in remaining_ids
