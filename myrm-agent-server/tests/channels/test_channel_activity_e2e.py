"""End-to-end test: Activity timestamps flow through Router → Bus → API schema."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncGenerator

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import (
    ChannelActivity,
    InboundMessage,
    OutboundMessage,
    ProgressUpdate,
)


class EchoChannel(BaseChannel):
    name = "echo"
    sent: list[OutboundMessage]

    def __init__(self) -> None:
        super().__init__()
        self.sent = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)


class StubPairingStore:
    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return "test-user"

    async def bind(self, channel: str, sender_id: str, user_id: str, **kwargs: object) -> None:
        pass

    async def unbind(self, channel: str, sender_id: str) -> None:
        pass

    async def get_status(self, channel: str, sender_id: str) -> str | None:
        return "active"


class StubExecutor:
    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        **kwargs: object,
    ) -> AsyncGenerator[ProgressUpdate | OutboundMessage]:
        yield OutboundMessage(
            channel=msg.channel,
            recipient_id=msg.chat_id or msg.sender_id,
            content="reply",
            user_id=user_id,
        )


class TestActivityE2E:
    @pytest.mark.asyncio
    async def test_outbound_records_activity(self) -> None:
        bus = MessageBus()
        ch = EchoChannel()
        bus.register_channel(ch)
        await bus.start()

        assert ch.activity.last_outbound_at is None

        before = time.time()
        await bus.publish_outbound(OutboundMessage(channel="echo", recipient_id="r1", content="hello", user_id="u1"))
        await asyncio.sleep(0.15)
        after = time.time()

        assert ch.activity.last_outbound_at is not None
        assert before <= ch.activity.last_outbound_at <= after
        assert len(ch.sent) == 1

        await bus.stop()

    @pytest.mark.asyncio
    async def test_inbound_records_activity(self) -> None:
        bus = MessageBus()
        ch = EchoChannel()
        bus.register_channel(ch)
        await bus.start()

        router = AgentRouter(
            bus=bus,
            pairing_store=StubPairingStore(),  # type: ignore[arg-type]
            agent_executor=StubExecutor(),  # type: ignore[arg-type]
            session_gate_config=SessionGateConfig(debounce_window_ms=0),
        )
        router._running = True
        consume_task = asyncio.create_task(router._consume_loop())

        assert ch.activity.last_inbound_at is None

        before = time.time()
        msg = InboundMessage(
            channel="echo",
            chat_id="test-chat",
            sender_id="user1",
            content="ping",
            sent_at=before,
            sent_timezone="UTC",
            metadata={"message_id": "m1"},
        )
        await ch._dispatch_inbound(msg)
        await asyncio.sleep(0.3)
        after = time.time()

        assert ch.activity.last_inbound_at is not None
        assert before <= ch.activity.last_inbound_at <= after

        router._running = False
        consume_task.cancel()
        try:
            await consume_task
        except asyncio.CancelledError:
            pass
        await bus.stop()

    @pytest.mark.asyncio
    async def test_activity_independent_of_health(self) -> None:
        ch = EchoChannel()
        ch.health.record_failure("test error")
        ch.activity.record_inbound()

        assert ch.health.consecutive_failures == 1
        assert ch.activity.last_inbound_at is not None
        assert isinstance(ch.activity, ChannelActivity)

    @pytest.mark.asyncio
    async def test_last_active_at_reflects_both_directions(self) -> None:
        bus = MessageBus()
        ch = EchoChannel()
        bus.register_channel(ch)
        await bus.start()

        router = AgentRouter(
            bus=bus,
            pairing_store=StubPairingStore(),  # type: ignore[arg-type]
            agent_executor=StubExecutor(),  # type: ignore[arg-type]
            session_gate_config=SessionGateConfig(debounce_window_ms=0),
        )
        router._running = True
        consume_task = asyncio.create_task(router._consume_loop())

        msg = InboundMessage(
            channel="echo",
            chat_id="test-chat",
            sender_id="user1",
            content="hello",
            sent_at=time.time(),
            sent_timezone="UTC",
            metadata={"message_id": "m2"},
        )
        await ch._dispatch_inbound(msg)
        await asyncio.sleep(0.3)

        inbound_ts = ch.activity.last_inbound_at
        assert inbound_ts is not None

        await bus.publish_outbound(OutboundMessage(channel="echo", recipient_id="r1", content="reply", user_id="u1"))
        await asyncio.sleep(0.3)

        outbound_ts = ch.activity.last_outbound_at
        assert outbound_ts is not None
        assert outbound_ts >= inbound_ts
        assert ch.activity.last_active_at == outbound_ts

        router._running = False
        consume_task.cancel()
        try:
            await consume_task
        except asyncio.CancelledError:
            pass
        await bus.stop()
