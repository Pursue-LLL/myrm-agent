"""Tests for BaseChannel inbound pipeline: bot filter, dedup, allow_policy, debounce, activity."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine

import pytest

from app.channels.core.allow_policy import (
    AllowPolicy,
    ChatPolicy,
)
from app.channels.core.base import BaseChannel
from app.channels.types import (
    ChannelCapabilities,
    InboundMessage,
    OutboundMessage,
)


class StubChannel(BaseChannel):
    """Minimal concrete channel for testing the inbound pipeline."""

    name = "stub"
    capabilities = ChannelCapabilities()

    async def send(self, msg: OutboundMessage) -> str | None:
        return "sent_id"


def _make_msg(
    sender_id: str = "user1",
    content: str = "hello",
    chat_id: str = "chat1",
    message_id: str = "",
    is_group: bool = False,
    mentioned: bool = False,
) -> InboundMessage:
    return InboundMessage(
        channel="stub",
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        message_id=message_id,
        is_group=is_group,
        mentioned=mentioned,
    )


def _make_handler(received: list[InboundMessage]) -> Callable[[InboundMessage], Coroutine[object, object, None]]:
    async def handler(m: InboundMessage) -> None:
        received.append(m)

    return handler


class TestBotSelfFilter:
    @pytest.mark.asyncio
    async def test_filters_bot_own_messages(self) -> None:
        ch = StubChannel()
        ch._bot_id = "bot123"
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(sender_id="bot123"))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_passes_non_bot_messages(self) -> None:
        ch = StubChannel()
        ch._bot_id = "bot123"
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(sender_id="user1"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_no_filter_when_bot_id_empty(self) -> None:
        ch = StubChannel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(sender_id="anyone"))
        assert len(received) == 1


class TestDeduplication:
    @pytest.mark.asyncio
    async def test_dedup_drops_duplicate_message_id(self) -> None:
        ch = StubChannel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        msg = _make_msg(message_id="msg_001")
        await ch._emit_inbound(msg)
        await ch._emit_inbound(msg)
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_dedup_allows_different_message_ids(self) -> None:
        ch = StubChannel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(message_id="msg_001"))
        await ch._emit_inbound(_make_msg(message_id="msg_002"))
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_dedup_skipped_when_no_message_id(self) -> None:
        ch = StubChannel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(message_id=""))
        await ch._emit_inbound(_make_msg(message_id=""))
        assert len(received) == 2

    @pytest.mark.asyncio
    async def test_dedup_disabled_when_ttl_zero(self) -> None:
        ch = StubChannel()
        ch._dedup_ttl = 0.0
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        msg = _make_msg(message_id="msg_001")
        await ch._emit_inbound(msg)
        await ch._emit_inbound(msg)
        assert len(received) == 2


class TestAllowPolicyIntegration:
    @pytest.mark.asyncio
    async def test_denylist_blocks_sender(self) -> None:
        ch = StubChannel()
        ch.allow_policy = AllowPolicy(denylist=frozenset({"bad_user"}))
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(sender_id="bad_user"))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_allowlist_blocks_unlisted_sender(self) -> None:
        ch = StubChannel()
        ch.allow_policy = AllowPolicy(allowlist=frozenset({"vip_user"}))
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(sender_id="random_user"))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_allowlist_passes_listed_sender(self) -> None:
        ch = StubChannel()
        ch.allow_policy = AllowPolicy(allowlist=frozenset({"vip_user"}))
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(sender_id="vip_user"))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_group_mention_only_blocks_without_mention(self) -> None:
        ch = StubChannel()
        ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.MENTION_ONLY)
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(is_group=True, mentioned=False))
        assert len(received) == 0

    @pytest.mark.asyncio
    async def test_group_mention_only_passes_with_mention(self) -> None:
        ch = StubChannel()
        ch.allow_policy = AllowPolicy(group_policy=ChatPolicy.MENTION_ONLY)
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(is_group=True, mentioned=True))
        assert len(received) == 1

    @pytest.mark.asyncio
    async def test_dm_deny_blocks_direct_message(self) -> None:
        ch = StubChannel()
        ch.allow_policy = AllowPolicy(dm_policy=ChatPolicy.DENY)
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        await ch._emit_inbound(_make_msg(is_group=False))
        assert len(received) == 0


class TestDebounce:
    @pytest.mark.asyncio
    async def test_debounce_batches_rapid_messages(self) -> None:
        ch = StubChannel()
        ch._debounce_seconds = 0.05
        received: list[InboundMessage] = []

        async def handler(m: InboundMessage) -> None:
            received.append(m)

        ch.set_inbound_handler(handler)

        await ch._emit_inbound(_make_msg(content="first", chat_id="c1"))
        await ch._emit_inbound(_make_msg(content="second", chat_id="c1"))
        await ch._emit_inbound(_make_msg(content="third", chat_id="c1"))

        await asyncio.sleep(0.15)
        assert len(received) == 1
        assert received[0].content == "third"

    @pytest.mark.asyncio
    async def test_debounce_separate_chats_independent(self) -> None:
        ch = StubChannel()
        ch._debounce_seconds = 0.05
        received: list[InboundMessage] = []

        async def handler(m: InboundMessage) -> None:
            received.append(m)

        ch.set_inbound_handler(handler)

        await ch._emit_inbound(_make_msg(content="a", chat_id="c1"))
        await ch._emit_inbound(_make_msg(content="b", chat_id="c2"))

        await asyncio.sleep(0.15)
        assert len(received) == 2


class TestActivityTracking:
    @pytest.mark.asyncio
    async def test_inbound_records_activity(self) -> None:
        ch = StubChannel()
        received: list[InboundMessage] = []
        ch.set_inbound_handler(_make_handler(received))

        assert ch.activity.last_inbound_at is None
        await ch._emit_inbound(_make_msg())
        assert ch.activity.last_inbound_at is not None

    @pytest.mark.asyncio
    async def test_no_handler_still_records_activity(self) -> None:
        ch = StubChannel()
        assert ch.activity.last_inbound_at is None
        await ch._emit_inbound(_make_msg())
        assert ch.activity.last_inbound_at is not None


class TestBuildInbound:
    def test_auto_populates_channel_name(self) -> None:
        ch = StubChannel()
        msg = ch._build_inbound(sender_id="u1", content="hi", chat_id="c1")
        assert msg.channel == "stub"
        assert msg.sender_id == "u1"
        assert msg.content == "hi"
        assert msg.chat_id == "c1"
