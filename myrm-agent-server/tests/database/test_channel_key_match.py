"""``channel_key_extends`` and ``channel_key_epochs`` select a conversation's keys at the segment boundary."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channels.types import InboundMessage, SessionPolicy, SessionResetMode
from app.core.channel_bridge.agent_executor.session import _build_session_key, resolve_session_key
from app.database.models.chat import Chat
from app.database.repositories.channel_key_match import channel_key_epochs, channel_key_extends
from app.services.chat.handoff import _build_target_session_key
from tests.support.channel_chat_rows import seed_channel_chat

_BASE = "telegram:dm:u1"
_OWN = [
    _BASE,
    f"{_BASE}:e=2026-01-01",
    f"{_BASE}:e=20260101T0000",
]
_CONTINUATIONS = [
    f"{_BASE}:thread:t1",
    f"{_BASE}:thread:t1:e=2026-01-01",
    f"{_BASE}:agent:a1:e=20260101T0000",
]
_OTHERS = [
    "telegram:dm:u10:e=2026-01-01",
    "telegram:dm:u1x",
    "telegram:dm:u",
    "slack:dm:u1",
]


async def _matched(db: AsyncSession, match: ColumnElement[bool]) -> set[str]:
    keys = (await db.execute(select(Chat.channel_session_key).where(match))).scalars()
    return {key for key in keys if key is not None}


@pytest.mark.asyncio
async def test_extends_matches_the_key_and_every_continuation_of_it(db_session: AsyncSession) -> None:
    for key in [*_OWN, *_CONTINUATIONS, *_OTHERS]:
        await seed_channel_chat(db_session, key)

    assert await _matched(db_session, channel_key_extends(_BASE)) == {*_OWN, *_CONTINUATIONS}


@pytest.mark.asyncio
async def test_epochs_match_the_key_and_its_epoch_keys_only(db_session: AsyncSession) -> None:
    for key in [*_OWN, *_CONTINUATIONS, *_OTHERS]:
        await seed_channel_chat(db_session, key)

    assert await _matched(db_session, channel_key_epochs(_BASE)) == set(_OWN)


@pytest.mark.asyncio
@pytest.mark.parametrize("match", [channel_key_extends, channel_key_epochs])
async def test_an_underscore_matches_only_an_underscore(
    db_session: AsyncSession, match: Callable[[str], ColumnElement[bool]]
) -> None:
    await seed_channel_chat(db_session, "telegram:dm:u_1:e=2026-01-01")
    await seed_channel_chat(db_session, "telegram:dm:ux1:e=2026-01-01")

    assert await _matched(db_session, match("telegram:dm:u_1")) == {"telegram:dm:u_1:e=2026-01-01"}


@pytest.mark.asyncio
async def test_the_epoch_keys_every_policy_writes_are_matched(db_session: AsyncSession) -> None:
    """The match reads the key format the resolver and the handoff write, so it has to follow any change to it."""
    msg = InboundMessage(channel="telegram", sender_id="u1", content="hi")
    base = _build_session_key(msg)
    written = {
        await resolve_session_key(msg, SessionPolicy(mode=SessionResetMode.PERSISTENT)),
        await resolve_session_key(msg, SessionPolicy(mode=SessionResetMode.DAILY)),
        await resolve_session_key(msg, SessionPolicy(mode=SessionResetMode.PERSISTENT), force_new_epoch=True),
        _build_target_session_key("telegram", "u1", SessionPolicy(mode=SessionResetMode.IDLE)),
        _build_target_session_key("telegram", "u1", SessionPolicy(mode=SessionResetMode.DAILY)),
    }
    for key in written:
        await seed_channel_chat(db_session, key)

    assert await _matched(db_session, channel_key_epochs(base)) == written
