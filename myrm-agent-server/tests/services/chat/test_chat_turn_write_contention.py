"""Undo, retry and a rewind's delete must not lose their write to a writer that commits between their read and their delete.

Each of them reads the chat and its messages, then deletes rows. Under the deferred-read transaction policy another
writer committing in between aborts the delete with SQLITE_BUSY_SNAPSHOT, which ``busy_timeout`` does not cover: an IM
``/undo`` or ``/retry`` answers a failure, and a rewind that has already reverted files leaves the conversation as it
was. The tests run the real transaction policy on a file database; the plain in-memory engines do not run it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.database.dto import MessageDTO
from app.database.models import Chat, Message
from app.database.repositories.chat_repo import ChatRepository
from app.database.repositories.uow import BoundChatRepository
from app.services.chat.chat_helpers import RetryResult, RewindResult, UndoResult
from app.services.chat.chat_service import ChatService
from tests.support.policy_sqlite import BUSY_TIMEOUT_MS, PolicyDb, policy_database

pytestmark = pytest.mark.usefixtures("rewind_collaborators")

CHAT_ID = "chat-turn-contended"
FIRST_ROW_AT = datetime(2025, 1, 1, 12, 0, 0)
# Long enough for a writer that nothing holds back to commit, short enough to keep the suite quick.
OTHER_WRITER_GRACE_S = 0.3

TurnResult = RewindResult | UndoResult | RetryResult


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "chat.db", monkeypatch) as db:
        # ``UnitOfWork`` keeps its own reference to the session factory, so patching the connection module is not enough.
        monkeypatch.setattr("app.database.repositories.uow.get_session_factory", lambda: db.factory)
        yield db


def _message(message_id: str, role: str, content: str, at_second: int) -> MessageDTO:
    created_at = FIRST_ROW_AT + timedelta(seconds=at_second)
    return MessageDTO(
        id=message_id,
        chat_id=CHAT_ID,
        role=role,
        content=content,
        sent_at=created_at,
        sent_timezone="UTC",
        created_at=created_at,
    )


async def _seed_two_turns(db: PolicyDb) -> None:
    async with db.factory() as session:
        session.add(Chat(id=CHAT_ID, title="Test", source="web"))
        await session.flush()
        await ChatRepository.add_messages(
            session,
            [
                _message("u1", "user", "Q1", 0),
                _message("a1", "assistant", "A1", 1),
                _message("u2", "user", "Q2", 2),
                _message("a2", "assistant", "A2", 3),
            ],
        )
        await session.commit()


async def _stored_ids(db: PolicyDb) -> list[str]:
    async with db.factory() as session:
        return sorted((await session.execute(select(Message.id).where(Message.chat_id == CHAT_ID))).scalars().all())


async def _commit_another_chat(db: PolicyDb) -> None:
    async with db.factory() as other:
        other.add(Chat(id="other-writer-chat"))
        await other.commit()


async def _run_while_another_writer_tries_to_commit(
    db: PolicyDb, monkeypatch: pytest.MonkeyPatch, unit: Callable[[], Awaitable[TurnResult]]
) -> TurnResult:
    """Run ``unit``; right before its delete, another writer tries to commit.

    A unit that took the write lock up front holds that writer back until it has committed. One that only has a read
    snapshot lets the writer through, and its own delete then fails with ``database is locked``.
    """
    delete = BoundChatRepository.delete_messages_after
    other_writer: asyncio.Task[None] | None = None
    other_writer_got_through: bool | None = None

    async def delete_after_another_writer_tried(
        self: BoundChatRepository,
        chat_id: str,
        anchor: MessageDTO,
        include_anchor: bool = False,
        only_ids: frozenset[str] | None = None,
    ) -> list[str]:
        nonlocal other_writer, other_writer_got_through
        # A rewind's delete is the first statement of its unit; read first so that the snapshot exists in every unit.
        await self.get_chat_by_id(chat_id)
        other_writer = asyncio.create_task(_commit_another_chat(db))
        done, _ = await asyncio.wait({other_writer}, timeout=OTHER_WRITER_GRACE_S)
        other_writer_got_through = bool(done)
        return await delete(self, chat_id, anchor, include_anchor, only_ids)

    monkeypatch.setattr(BoundChatRepository, "delete_messages_after", delete_after_another_writer_tried)

    result = await unit()

    assert other_writer is not None
    await asyncio.wait_for(other_writer, timeout=BUSY_TIMEOUT_MS / 1000)  # it gets the lock once the unit has committed
    assert other_writer_got_through is False
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("unit", "deleted_count", "kept_ids"),
    [
        pytest.param(lambda: ChatService.rewind_to_message(CHAT_ID, "u2"), 2, ["a1", "u1"], id="rewind"),
        pytest.param(lambda: ChatService.undo_last_turn(CHAT_ID), 2, ["a1", "u1"], id="undo"),
        pytest.param(lambda: ChatService.retry_last_turn(CHAT_ID), 1, ["a1", "u1", "u2"], id="retry"),
    ],
)
async def test_the_delete_keeps_its_write_when_another_writer_tries_to_commit_first(
    policy_db: PolicyDb,
    monkeypatch: pytest.MonkeyPatch,
    unit: Callable[[], Awaitable[TurnResult]],
    deleted_count: int,
    kept_ids: list[str],
) -> None:
    await _seed_two_turns(policy_db)

    result = await _run_while_another_writer_tries_to_commit(policy_db, monkeypatch, unit)

    assert result.success is True
    assert result.deleted_count == deleted_count
    assert await _stored_ids(policy_db) == kept_ids
