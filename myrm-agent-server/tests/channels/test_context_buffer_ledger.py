"""Persisted group context: a message is handed to a turn once, and only while it is fresh.

The in-memory buffer already drains once and expires entries; the ledger-backed path of
``GroupContextBuffer.drain_async`` must keep the same contract and must not hand a turn the
messages that already started a turn (the session transcript carries them).
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.channels.routing.context_buffer import GroupContextBuffer
from app.database.models.channel_message import ChannelMessageModel
from app.database.repositories.channel_message_repo import ChannelMessageRepository

_CHANNEL = "feishu"


class _Ledger:
    """A throwaway channel ledger the data plane reads through a patched session factory."""

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker
        self._next_id = 0

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        async with self._maker() as session:
            yield session

    async def add(
        self,
        chat_id: str,
        content: str,
        age: timedelta = timedelta(0),
        *,
        is_trigger: bool = False,
    ) -> None:
        self._next_id += 1
        async with self._maker() as session:
            await ChannelMessageRepository.record_message(
                session,
                ChannelMessageModel(
                    id=f"m{self._next_id}",
                    channel=_CHANNEL,
                    chat_id=chat_id,
                    sender_id="u1",
                    sender_name="Ann",
                    content=content,
                    is_trigger=is_trigger,
                    is_self=False,
                    created_at=datetime.now(timezone.utc) - age,
                ),
            )
            await session.commit()


@pytest.fixture
async def ledger() -> AsyncIterator[_Ledger]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(
            lambda sync_conn: ChannelMessageModel.metadata.create_all(sync_conn, tables=[ChannelMessageModel.__table__])
        )
    store = _Ledger(async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession))
    with patch("app.channels.routing.channel_data_plane.get_session", store.session):
        yield store
    await engine.dispose()


async def _drain(buffer: GroupContextBuffer, chat_id: str) -> list[str]:
    return [entry.content for entry in await buffer.drain_async(_CHANNEL, chat_id)]


async def test_messages_older_than_the_expiry_are_not_handed_out(ledger: _Ledger) -> None:
    await ledger.add("g1", "three days ago", timedelta(days=3))
    await ledger.add("g1", "two minutes ago", timedelta(minutes=2))

    assert await _drain(GroupContextBuffer(), "g1") == ["two minutes ago"]


async def test_a_message_is_handed_out_once(ledger: _Ledger) -> None:
    buffer = GroupContextBuffer()
    await ledger.add("g1", "first", timedelta(minutes=2))
    assert await _drain(buffer, "g1") == ["first"]

    assert await _drain(buffer, "g1") == []

    await ledger.add("g1", "second")
    assert await _drain(buffer, "g1") == ["second"]


async def test_a_message_that_started_a_turn_is_not_observed_context(ledger: _Ledger) -> None:
    await ledger.add("g1", "chatter", timedelta(minutes=3))
    await ledger.add("g1", "@bot an earlier request", timedelta(minutes=2), is_trigger=True)

    assert await _drain(GroupContextBuffer(), "g1") == ["chatter"]


async def test_one_chat_taking_its_context_leaves_another_chat_untouched(ledger: _Ledger) -> None:
    buffer = GroupContextBuffer()
    await ledger.add("g1", "in g1", timedelta(minutes=2))
    await ledger.add("g2", "in g2", timedelta(minutes=2))

    assert await _drain(buffer, "g1") == ["in g1"]
    assert await _drain(buffer, "g2") == ["in g2"]


@pytest.mark.parametrize(
    "forget",
    [lambda buffer: buffer.clear("g1"), lambda buffer: buffer.clear_all()],
    ids=["clear", "clear_all"],
)
async def test_clearing_a_chat_forgets_what_was_taken(ledger: _Ledger, forget: Callable[[GroupContextBuffer], None]) -> None:
    buffer = GroupContextBuffer()
    await ledger.add("g1", "chatter", timedelta(minutes=2))
    assert await _drain(buffer, "g1") == ["chatter"]

    forget(buffer)

    assert await _drain(buffer, "g1") == ["chatter"]
