"""Which conversation an inbound channel message lands in: the session key built from the message."""

from __future__ import annotations

import pytest

from app.channels.types import InboundMessage, SessionPolicy, SessionResetMode
from app.core.channel_bridge.agent_executor.session import _build_session_key, resolve_session_key

_GROUP_THREAD_KEY = "discord:group:forum-456:thread:thread-789"


def _msg(
    *,
    sender_id: str = "user-123",
    chat_id: str = "forum-456",
    is_group: bool = True,
    thread_id: str | None = "thread-789",
) -> InboundMessage:
    return InboundMessage(
        channel="discord",
        sender_id=sender_id,
        chat_id=chat_id,
        content="Hello",
        is_group=is_group,
        thread_id=thread_id,
        sent_at=1234567890.0,
        sent_timezone="UTC",
    )


class TestBuildSessionKey:
    def test_the_members_of_a_group_thread_share_one_key(self) -> None:
        first = _build_session_key(_msg(sender_id="user-123"))
        second = _build_session_key(_msg(sender_id="user-456"))

        assert first == second == _GROUP_THREAD_KEY

    def test_each_dm_sender_has_their_own_key(self) -> None:
        first = _build_session_key(_msg(sender_id="user-123", chat_id="dm-1", is_group=False, thread_id=None))
        second = _build_session_key(_msg(sender_id="user-456", chat_id="dm-1", is_group=False, thread_id=None))

        assert (first, second) == ("discord:dm:user-123", "discord:dm:user-456")

    def test_the_agent_is_a_dimension_of_the_key(self) -> None:
        assert _build_session_key(_msg(), agent_id="agent-xyz") == f"{_GROUP_THREAD_KEY}:agent:agent-xyz"


@pytest.mark.asyncio
class TestResolveSessionKey:
    async def test_the_persistent_policy_resolves_to_the_base_key(self) -> None:
        key = await resolve_session_key(_msg(), SessionPolicy(mode=SessionResetMode.PERSISTENT))

        assert key == _GROUP_THREAD_KEY

    async def test_the_daily_policy_appends_the_reset_epoch_to_the_base_key(self) -> None:
        key = await resolve_session_key(_msg(), SessionPolicy(mode=SessionResetMode.DAILY, daily_reset_hour=4))

        base, separator, epoch = key.partition(":e=")
        assert (base, separator) == (_GROUP_THREAD_KEY, ":e=")
        assert epoch
