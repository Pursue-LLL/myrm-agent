"""Resolving a channel chat must not lose its write to a writer that commits between its read and its write.

The first message of every IM conversation after the session reset hour creates a chat, and an agent rebind updates one.
Both read the chat by its session key and then write. Under the deferred-read transaction policy another writer
committing in between aborts the write with SQLITE_BUSY_SNAPSHOT, which ``busy_timeout`` does not cover, and the message
that triggered the lookup is answered with an error and never processed. A chat that exists and needs no rebind is
returned from a plain read, which no writer can hold back. The tests run the real transaction policy on a file database.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Coroutine
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.database.dto import ChatDTO
from app.database.models import Chat
from app.services.chat.chat_service import ChatService
from tests.support.policy_sqlite import BUSY_TIMEOUT_MS, PolicyDb, hold_write_lock, policy_database, wait_until

SESSION_KEY = "telegram:dm:42:epoch-1"
BOUND_CHAT_ID = "chat-bound"
# How long a resolve that took the write lock first is watched for a write while the holder keeps the lock.
LOCKED_OUT_WRITE_WATCH_S = 0.5
# A chat returned without a write comes back long before this, while another writer still holds the lock.
UNBLOCKED_READ_DEADLINE_S = 2.0
CONCURRENT_KEY_ROUNDS = 10


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "chat.db", monkeypatch) as db:
        # ``UnitOfWork`` keeps its own reference to the session factory, so patching the connection module is not enough.
        monkeypatch.setattr("app.database.repositories.uow.get_session_factory", lambda: db.factory)
        yield db


async def _seed_bound_chat(db: PolicyDb, agent_id: str) -> None:
    async with db.factory() as session:
        session.add(Chat(id=BOUND_CHAT_ID, agent_id=agent_id, source="telegram", channel_session_key=SESSION_KEY))
        await session.commit()


async def _chats_under(db: PolicyDb, session_key: str) -> list[tuple[str, str | None]]:
    async with db.factory() as session:
        rows = await session.execute(select(Chat.id, Chat.agent_id).where(Chat.channel_session_key == session_key))
        return [(chat_id, agent_id) for chat_id, agent_id in rows]


async def _resolve_while_another_writer_holds_the_lock(
    db: PolicyDb, resolve: Callable[[], Coroutine[object, object, ChatDTO]]
) -> ChatDTO:
    """Start ``resolve`` against a database whose write lock another writer holds, then let that writer commit.

    A resolve that reads before it takes the lock issues its write on the snapshot it read, so the holder commits only
    after that write was issued and the write is lost. One that takes the lock first issues no write while the holder
    keeps it, so the holder commits once the watch period has passed, and the write then goes through.
    """
    holder = await hold_write_lock(db)
    try:
        resolution = asyncio.create_task(resolve())
        await wait_until(db.write_issued, LOCKED_OUT_WRITE_WATCH_S)
        await holder.commit()
        return await asyncio.wait_for(resolution, timeout=BUSY_TIMEOUT_MS / 1000)
    finally:
        await holder.close()


@pytest.mark.asyncio
async def test_a_new_chat_is_created_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    chat = await _resolve_while_another_writer_holds_the_lock(
        policy_db, lambda: ChatService.get_or_create_channel_chat(SESSION_KEY, "telegram")
    )

    assert chat.channel_session_key == SESSION_KEY
    assert await _chats_under(policy_db, SESSION_KEY) == [(chat.id, None)]


@pytest.mark.asyncio
async def test_a_rebind_is_stored_when_another_writer_commits_first(policy_db: PolicyDb) -> None:
    await _seed_bound_chat(policy_db, "agent-old")

    chat = await _resolve_while_another_writer_holds_the_lock(
        policy_db, lambda: ChatService.get_or_create_channel_chat(SESSION_KEY, "telegram", agent_id="agent-new")
    )

    assert chat.agent_id == "agent-new"
    assert await _chats_under(policy_db, SESSION_KEY) == [(BOUND_CHAT_ID, "agent-new")]


@pytest.mark.asyncio
async def test_a_bound_chat_is_returned_without_waiting_for_the_write_lock(policy_db: PolicyDb) -> None:
    await _seed_bound_chat(policy_db, "agent-1")
    holder = await hold_write_lock(policy_db)
    try:
        chat = await asyncio.wait_for(
            ChatService.get_or_create_channel_chat(SESSION_KEY, "telegram", agent_id="agent-1"),
            timeout=UNBLOCKED_READ_DEADLINE_S,
        )
    finally:
        await holder.close()

    assert chat.id == BOUND_CHAT_ID


@pytest.mark.asyncio
async def test_concurrent_creators_of_one_key_share_one_chat(policy_db: PolicyDb) -> None:
    for round_index in range(CONCURRENT_KEY_ROUNDS):
        key = f"{SESSION_KEY}:round-{round_index}"

        first, second = await asyncio.wait_for(
            asyncio.gather(
                ChatService.get_or_create_channel_chat(key, "telegram"),
                ChatService.get_or_create_channel_chat(key, "telegram"),
            ),
            timeout=BUSY_TIMEOUT_MS / 1000,
        )

        assert first.id == second.id
        assert await _chats_under(policy_db, key) == [(first.id, None)]
