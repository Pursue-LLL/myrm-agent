"""Tests for truncate_after_message: edit-resend backend data consistency."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.dto import MessageDTO
from app.database.repositories.chat_repo import ChatRepository
from app.database.models import Chat
from app.services.chat.chat_service import ChatService


def _make_chat(chat_id: str = "test-chat") -> Chat:
    return Chat(id=chat_id, title="Test Chat", source="web")


def _make_msg(
    chat_id: str,
    role: str,
    content: str,
    *,
    msg_id: str | None = None,
    created_at: datetime | None = None,
) -> MessageDTO:
    ts = created_at or datetime.utcnow()
    return MessageDTO(
        id=msg_id or f"{role}-{content[:8]}",
        chat_id=chat_id,
        role=role,
        content=content,
        sent_at=ts,
        sent_timezone="UTC",
        created_at=ts,
    )


@pytest.fixture
async def seeded_chat(db_session: AsyncSession) -> tuple[str, list[MessageDTO]]:
    """Seed a chat with 4 messages: user1, assistant1, user2, assistant2."""
    chat_id = "truncate-test"
    db_session.add(_make_chat(chat_id))
    await db_session.flush()

    base = datetime(2025, 1, 1, 12, 0, 0)
    msgs = [
        _make_msg(chat_id, "user", "Hello", msg_id="u1", created_at=base),
        _make_msg(chat_id, "assistant", "Hi there", msg_id="a1", created_at=base + timedelta(seconds=1)),
        _make_msg(chat_id, "user", "Edit this", msg_id="u2", created_at=base + timedelta(seconds=2)),
        _make_msg(chat_id, "assistant", "Old response", msg_id="a2", created_at=base + timedelta(seconds=3)),
    ]
    await ChatRepository.add_messages(db_session, msgs)
    await db_session.commit()
    return chat_id, msgs


class TestTruncateAfterMessage:
    """Edit-resend truncation tests."""

    async def test_truncate_deletes_target_and_later(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        chat_id, _ = seeded_chat

        result = await ChatService.truncate_after_message(chat_id, "u2")

        assert result.success is True
        assert result.deleted_count == 2

        remaining = await ChatRepository.get_all_messages(db_session, chat_id)
        assert len(remaining) == 2
        assert remaining[0].id == "u1"
        assert remaining[1].id == "a1"

    async def test_truncate_nonexistent_message_returns_failure(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        chat_id, _ = seeded_chat

        result = await ChatService.truncate_after_message(chat_id, "nonexistent")

        assert result.success is False
        assert result.deleted_count == 0

    async def test_truncate_nonexistent_chat_returns_failure(self, db_session: AsyncSession) -> None:
        result = await ChatService.truncate_after_message("no-such-chat", "u1")

        assert result.success is False
        assert result.deleted_count == 0

    async def test_truncate_first_message_clears_all(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        chat_id, _ = seeded_chat

        result = await ChatService.truncate_after_message(chat_id, "u1")

        assert result.success is True
        assert result.deleted_count == 4

        remaining = await ChatRepository.get_all_messages(db_session, chat_id)
        assert len(remaining) == 0

    async def test_truncate_last_message_deletes_only_it(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        chat_id, _ = seeded_chat

        result = await ChatService.truncate_after_message(chat_id, "a2")

        assert result.success is True
        assert result.deleted_count == 1

        remaining = await ChatRepository.get_all_messages(db_session, chat_id)
        assert len(remaining) == 3
        assert [m.id for m in remaining] == ["u1", "a1", "u2"]


    async def test_truncate_updates_last_message_preview(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        """After truncating, chat.last_message should reflect the new tail."""
        chat_id, _ = seeded_chat

        await ChatService.truncate_after_message(chat_id, "u2")

        from sqlalchemy import select

        chat = (await db_session.execute(select(Chat).where(Chat.id == chat_id))).scalar_one()
        assert chat.last_message is not None
        assert "Hi there" in chat.last_message

    async def test_truncate_empty_chat(self, db_session: AsyncSession) -> None:
        """Truncating a chat with zero messages returns failure (message not found)."""
        chat_id = "empty-chat"
        db_session.add(_make_chat(chat_id))
        await db_session.flush()
        await db_session.commit()

        result = await ChatService.truncate_after_message(chat_id, "nonexistent")

        assert result.success is False
        assert result.deleted_count == 0

    async def test_truncate_idempotent(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        """Truncating an already-deleted message returns failure gracefully."""
        chat_id, _ = seeded_chat

        first = await ChatService.truncate_after_message(chat_id, "u2")
        assert first.success is True
        assert first.deleted_count == 2

        second = await ChatService.truncate_after_message(chat_id, "u2")
        assert second.success is False
        assert second.deleted_count == 0

    async def test_truncate_single_message_chat(self, db_session: AsyncSession) -> None:
        """Chat with exactly one message: truncating it leaves an empty chat."""
        chat_id = "single-msg"
        db_session.add(_make_chat(chat_id))
        await db_session.flush()

        msg = _make_msg(chat_id, "user", "Only msg", msg_id="solo")
        await ChatRepository.add_messages(db_session, [msg])
        await db_session.commit()

        result = await ChatService.truncate_after_message(chat_id, "solo")

        assert result.success is True
        assert result.deleted_count == 1

        remaining = await ChatRepository.get_all_messages(db_session, chat_id)
        assert len(remaining) == 0


class TestGetMessageById:
    """Repository-level get_message_by_id tests."""

    async def test_returns_message_when_found(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        chat_id, _ = seeded_chat

        msg = await ChatRepository.get_message_by_id(db_session, chat_id, "u1")

        assert msg is not None
        assert msg.id == "u1"
        assert msg.content == "Hello"

    async def test_returns_none_for_wrong_chat(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        msg = await ChatRepository.get_message_by_id(db_session, "wrong-chat", "u1")

        assert msg is None

    async def test_returns_none_for_nonexistent_id(
        self, db_session: AsyncSession, seeded_chat: tuple[str, list[MessageDTO]]
    ) -> None:
        chat_id, _ = seeded_chat

        msg = await ChatRepository.get_message_by_id(db_session, chat_id, "nonexistent")

        assert msg is None
