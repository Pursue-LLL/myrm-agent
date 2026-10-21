"""Persisting the user's message against a real WAL SQLite engine while other writers are active.

The append reads the chat first and writes the message afterwards. If another writer could commit in between,
SQLite would abort the write at once with "database is locked" (SQLITE_BUSY_SNAPSHOT, which ``busy_timeout``
does not cover) and the turn carrying the message would fail setup before the agent starts. The append therefore
takes the write lock up front: competing writers wait, and the message is always stored.
"""

from __future__ import annotations

import asyncio
import sqlite3
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.factory import register_sqlite_transaction_events
from app.database.migrations import ensure_raw_sql_schema
from app.database.models import Base, Chat, Message
from app.database.repositories.uow import BoundChatRepository
from app.services.chat.chat_service import ChatService

_CHAT_ID = "chat-contended"
_BUSY_TIMEOUT_MS = 5_000  # long enough that a writer waiting for the lock never times out in these tests


def _set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _record: object) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
    cursor.close()


@pytest.fixture()
async def session_factory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'chat.db'}",
        future=True,
        connect_args={"check_same_thread": False},
        pool_size=3,
        max_overflow=1,
    )
    event.listen(engine.sync_engine, "connect", _set_sqlite_pragma)
    register_sqlite_transaction_events(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await ensure_raw_sql_schema(engine)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr("app.database.repositories.uow.get_session_factory", lambda: factory)
    async with factory() as session:
        session.add(Chat(id=_CHAT_ID, agent_id="agent-1"))
        await session.commit()
    yield factory
    await engine.dispose()


async def _append_user_message(message_id: str) -> None:
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=_CHAT_ID,
        content="run the audit command",
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id=message_id,
    )


async def _commit_chat(session_factory: async_sessionmaker[AsyncSession], chat_id: str) -> None:
    async with session_factory() as other:
        other.add(Chat(id=chat_id))
        await other.commit()


@pytest.mark.asyncio
async def test_a_competing_writer_waits_until_the_message_is_committed(
    session_factory: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read_message = BoundChatRepository.get_message_by_id
    competitor: asyncio.Task[None] | None = None
    competitor_committed_mid_append: bool | None = None

    async def read_while_a_competitor_tries_to_commit(self: BoundChatRepository, chat_id: str, message_id: str) -> object:
        nonlocal competitor, competitor_committed_mid_append
        if competitor is None:
            competitor = asyncio.create_task(_commit_chat(session_factory, "other-writer-chat"))
            done, _ = await asyncio.wait({competitor}, timeout=0.3)
            competitor_committed_mid_append = bool(done)
        return await read_message(self, chat_id, message_id)

    monkeypatch.setattr(BoundChatRepository, "get_message_by_id", read_while_a_competitor_tries_to_commit)

    await _append_user_message("msg-contended")

    assert competitor is not None
    await competitor  # it gets the lock once the append has committed
    assert competitor_committed_mid_append is False
    async with session_factory() as session:
        stored = (await session.execute(select(Message.id).where(Message.chat_id == _CHAT_ID))).scalars().all()
        chat_count = (await session.execute(select(func.count()).select_from(Chat))).scalar_one()
    assert stored == ["msg-contended"]
    assert chat_count == 2


@pytest.mark.asyncio
async def test_parallel_appends_and_other_writers_all_commit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """More tasks than pooled connections: holding the write lock must never starve the pool."""
    message_ids = [f"msg-{index}" for index in range(8)]

    await asyncio.wait_for(
        asyncio.gather(
            *[_append_user_message(message_id) for message_id in message_ids],
            *[_commit_chat(session_factory, f"other-{index}") for index in range(8)],
        ),
        timeout=30,
    )

    async with session_factory() as session:
        stored = (await session.execute(select(Message.id).where(Message.chat_id == _CHAT_ID))).scalars().all()
        chat_count = (await session.execute(select(func.count()).select_from(Chat))).scalar_one()
    assert sorted(stored) == sorted(message_ids)
    assert chat_count == 1 + 8
