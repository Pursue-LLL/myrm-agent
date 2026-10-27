"""The idle reset policy continues a conversation's own chat and never another conversation's.

A channel session key is ``{channel}:{peer_kind}:{peer}[:thread:..][:agent:..]`` plus a reset epoch ``:e=..``. The idle
policy looks up the newest chat of the message's conversation; a key that merely starts with the same characters belongs
to another peer, topic or agent, and answering from its chat would show one conversation's history in another and bind
that chat to the wrong agent.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.types import InboundMessage, SessionPolicy, SessionResetMode
from app.core.channel_bridge.agent_executor.session import resolve_session_key
from tests.support.channel_chat_rows import seed_channel_chat

_POLICY = SessionPolicy(mode=SessionResetMode.IDLE, idle_minutes=120)
_BASE = "telegram:dm:u1"
_OWN_EPOCH_KEY = f"{_BASE}:e=20260101T0000"
_NEIGHBOUR_KEYS = {
    "longer peer id": "telegram:dm:u10:e=20260101T0000",
    "topic of the same peer": f"{_BASE}:thread:t1:e=20260101T0000",
    "agent of the same peer": f"{_BASE}:agent:a1:e=20260101T0000",
}


def _message(sender_id: str = "u1") -> InboundMessage:
    return InboundMessage(channel="telegram", sender_id=sender_id, content="hi")


@pytest.fixture(autouse=True)
def _database(db_session: AsyncSession) -> Iterator[None]:
    @asynccontextmanager
    async def session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    with patch("app.database.connection.get_session", session):
        yield


@pytest.mark.asyncio
async def test_a_chat_within_the_idle_window_is_continued(db_session: AsyncSession) -> None:
    await seed_channel_chat(db_session, _OWN_EPOCH_KEY, idle_minutes=10)

    assert await resolve_session_key(_message(), _POLICY) == _OWN_EPOCH_KEY


@pytest.mark.asyncio
async def test_a_chat_stored_under_the_bare_key_is_continued(db_session: AsyncSession) -> None:
    await seed_channel_chat(db_session, _BASE, idle_minutes=10)

    assert await resolve_session_key(_message(), _POLICY) == _BASE


@pytest.mark.asyncio
async def test_a_chat_past_the_idle_window_opens_a_new_epoch(db_session: AsyncSession) -> None:
    await seed_channel_chat(db_session, _OWN_EPOCH_KEY, idle_minutes=180)

    key = await resolve_session_key(_message(), _POLICY)

    assert key.startswith(f"{_BASE}:e=") and key != _OWN_EPOCH_KEY


@pytest.mark.asyncio
async def test_a_first_message_opens_the_first_epoch() -> None:
    assert (await resolve_session_key(_message(), _POLICY)).startswith(f"{_BASE}:e=")


@pytest.mark.asyncio
@pytest.mark.parametrize("neighbour", _NEIGHBOUR_KEYS.values(), ids=_NEIGHBOUR_KEYS.keys())
async def test_another_conversations_chat_is_not_continued(db_session: AsyncSession, neighbour: str) -> None:
    await seed_channel_chat(db_session, neighbour, idle_minutes=1)

    key = await resolve_session_key(_message(), _POLICY)

    assert key.startswith(f"{_BASE}:e=") and key != neighbour


@pytest.mark.asyncio
@pytest.mark.parametrize("neighbour", _NEIGHBOUR_KEYS.values(), ids=_NEIGHBOUR_KEYS.keys())
async def test_the_own_chat_wins_over_a_more_recent_neighbour(db_session: AsyncSession, neighbour: str) -> None:
    await seed_channel_chat(db_session, _OWN_EPOCH_KEY, idle_minutes=30)
    await seed_channel_chat(db_session, neighbour, idle_minutes=1)

    assert await resolve_session_key(_message(), _POLICY) == _OWN_EPOCH_KEY


@pytest.mark.asyncio
async def test_an_underscore_in_the_peer_id_matches_only_itself(db_session: AsyncSession) -> None:
    """``_`` is a single-character wildcard in a ``LIKE`` pattern, and peer ids keep it when they are sanitised."""
    await seed_channel_chat(db_session, "telegram:dm:ux1:e=20260101T0000", idle_minutes=1)

    key = await resolve_session_key(_message("u_1"), _POLICY)

    assert key.startswith("telegram:dm:u_1:e=")
