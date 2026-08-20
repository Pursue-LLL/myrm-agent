"""End-to-end integration test: WeCom AI Bot and Self-built streaming pipeline with Router."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.core.bus import MessageBus
from app.channels.providers.wecom.aibot_channel import WeComAiBotChannel, WeComStreamState
from app.channels.providers.wecom.channel import WeComChannel
from app.channels.routing.router import AgentRouter
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import (
    InboundMessage,
    OutboundMessage,
    ProgressUpdate,
    StreamingText,
)


class StubPairingStore:
    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return "test-user"

    async def bind(self, channel: str, sender_id: str, user_id: str, **kwargs: object) -> None:
        pass

    async def unbind(self, channel: str, sender_id: str) -> None:
        pass

    async def get_status(self, channel: str, sender_id: str) -> str | None:
        return "active"


class StubStreamingExecutor:
    async def execute_stream(
        self,
        msg: InboundMessage,
        user_id: str,
        **kwargs: object,
    ) -> AsyncGenerator[ProgressUpdate | StreamingText | OutboundMessage]:
        # 1. Progress step
        yield ProgressUpdate(
            label="searching documentation for api",
        )
        await asyncio.sleep(0.01)

        # 2. Streaming text with thinking tokens
        yield StreamingText(
            text="<think>Planning the response...</think>Here is the detailed result for WeCom integration.",
        )
        await asyncio.sleep(0.01)

        # 3. Final answer
        yield OutboundMessage(
            channel=msg.channel,
            recipient_id=msg.chat_id or msg.sender_id,
            content="Here is the detailed result for WeCom integration.",
            user_id=user_id,
        )


@pytest.mark.asyncio
async def test_wecom_aibot_overflow_chunks_lifecycle_integration() -> None:
    """Integration: super-long answers split into chunks, morphing first chunk and sending rest via proactive."""
    bus = MessageBus()
    ch = WeComAiBotChannel(bot_id="test_bot", secret="test_secret")
    mock_ws = AsyncMock()
    ch._ws = mock_ws
    bus.register_channel(ch)
    await bus.start()

    ch._active_streams["stream_long"] = WeComStreamState(
        stream_id="stream_long", chat_id="chat_long", req_id="req_long"
    )

    class LongAnswerExecutor:
        async def execute_stream(
            self,
            msg: InboundMessage,
            user_id: str,
            **kwargs: object,
        ) -> AsyncGenerator[ProgressUpdate | OutboundMessage]:
            yield ProgressUpdate(label="generating large report")
            await asyncio.sleep(0.01)
            # Long content that exceeds chunk limit
            yield OutboundMessage(
                channel=msg.channel,
                recipient_id=msg.chat_id or msg.sender_id,
                content="Chunk 1 content\n\nChunk 2 overflow\n\nChunk 3 overflow",
                user_id=user_id,
            )

    router = AgentRouter(
        bus=bus,
        pairing_store=StubPairingStore(),  # type: ignore[arg-type]
        agent_executor=LongAnswerExecutor(),  # type: ignore[arg-type]
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )
    router._running = True
    consume_task = asyncio.create_task(router._consume_loop())

    inbound = InboundMessage(
        channel="wecom_aibot",
        chat_id="chat_long",
        sender_id="u_long",
        content="generate large report",
        thread_id="req_long",
        metadata={"message_id": "stream_long", "req_id": "req_long"},
    )

    with patch("app.channels.providers.wecom.aibot_channel.render", return_value=["Chunk 1", "Chunk 2", "Chunk 3"]):
        await ch._dispatch_inbound(inbound)
        await asyncio.sleep(0.8)

    # Assert 1 respond_msg (first chunk finished) + 2 proactive aibot_send_msg
    sent_payloads = [json.loads(call[0][0]) for call in mock_ws.send.call_args_list]
    respond_msgs = [p for p in sent_payloads if p.get("cmd") == "aibot_respond_msg"]
    proactive_msgs = [p for p in sent_payloads if p.get("cmd") == "aibot_send_msg"]

    assert len(respond_msgs) >= 1
    assert any(p.get("body", {}).get("stream", {}).get("finish") is True for p in respond_msgs)
    assert len(proactive_msgs) == 2

    router._running = False
    consume_task.cancel()
    try:
        await consume_task
    except asyncio.CancelledError:
        pass
    await bus.stop()


@pytest.mark.asyncio
async def test_wecom_aibot_reconnect_recovery_integration() -> None:
    """Integration: stream marked is_force_closed during WS drop delivers final answer upon completion."""
    bus = MessageBus()
    ch = WeComAiBotChannel(bot_id="test_bot", secret="test_secret")
    mock_ws = AsyncMock()
    ch._ws = mock_ws
    bus.register_channel(ch)
    await bus.start()

    # Pre-mark stream as force closed (simulating reconnect drop)
    ch._active_streams["stream_reconnect"] = WeComStreamState(
        stream_id="stream_reconnect", chat_id="chat_rec", req_id="req_rec", is_force_closed=True
    )

    router = AgentRouter(
        bus=bus,
        pairing_store=StubPairingStore(),  # type: ignore[arg-type]
        agent_executor=StubStreamingExecutor(),  # type: ignore[arg-type]
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )
    router._running = True
    consume_task = asyncio.create_task(router._consume_loop())

    inbound = InboundMessage(
        channel="wecom_aibot",
        chat_id="chat_rec",
        sender_id="u_rec",
        content="query during reconnect",
        thread_id="req_rec",
        metadata={"message_id": "stream_reconnect", "req_id": "req_rec"},
    )
    await ch._dispatch_inbound(inbound)
    await asyncio.sleep(0.5)

    sent_payloads = [json.loads(call[0][0]) for call in mock_ws.send.call_args_list]
    # In force-closed state, respond_msg finishes the stream
    assert any(p.get("cmd") == "aibot_respond_msg" for p in sent_payloads)

    router._running = False
    consume_task.cancel()
    try:
        await consume_task
    except asyncio.CancelledError:
        pass
    await bus.stop()


@pytest.mark.asyncio
async def test_wecom_self_built_router_no_zombie_integration() -> None:
    bus = MessageBus()
    ch = WeComChannel(corp_id="corp1", corp_secret="sec1", agent_id="10001")
    bus.register_channel(ch)
    await bus.start()

    # Mock _api_send to capture outbound messages
    sent_api_calls: list[dict[str, object]] = []

    ch._token = "valid_mock_token"
    ch._token_expires_at = 9999999999.0

    async def _mock_api_send(touser: str, msgtype: str, content: dict[str, object], **kwargs: object) -> bool:
        sent_api_calls.append({"touser": touser, "msgtype": msgtype, "content": content})
        return True

    ch._api_send = _mock_api_send  # type: ignore[assignment]

    router = AgentRouter(
        bus=bus,
        pairing_store=StubPairingStore(),  # type: ignore[arg-type]
        agent_executor=StubStreamingExecutor(),  # type: ignore[arg-type]
        session_gate_config=SessionGateConfig(debounce_window_ms=0),
    )
    router._running = True
    consume_task = asyncio.create_task(router._consume_loop())

    inbound = InboundMessage(
        channel="wecom",
        chat_id="user_2",
        sender_id="user_2",
        content="hello",
        metadata={"message_id": "m_self_built"},
    )
    await ch._dispatch_inbound(inbound)
    await asyncio.sleep(0.5)

    # Verify NO zombie placeholder "Thinking..." was sent, only final result delivered
    assert len(sent_api_calls) == 1
    assert "detailed result for WeCom integration" in str(sent_api_calls[0]["content"])

    router._running = False
    consume_task.cancel()
    try:
        await consume_task
    except asyncio.CancelledError:
        pass
    await bus.stop()
