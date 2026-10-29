"""What a wake turn says reaches the IM chat its conversation lives in, from the settlement to the channel.

The real service, scheduler, carrier, gateway, router and bus; the stand-ins are the chat store, the budget, the event
bus, the turn the wake would stream (it needs a model) and the channel (it needs a platform).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupEvent, WakeupSourceType

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ChannelCapabilities, InboundMessage, OutboundMessage
from app.core.channel_bridge.wake_return import ChannelWakeReplyReturner, WakeOrigins
from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service, wake_turn_scheduler
from app.services.agent.adaptive_wakeup import service as service_module
from app.services.agent.adaptive_wakeup.reply_return import set_wake_reply_returner
from app.services.agent.gateway import get_agent_gateway

_REPLY = "The research is done: three sources agree."


class _Pingchat(BaseChannel):
    """An IM platform that records what the bot said."""

    name = "pingchat"
    capabilities = ChannelCapabilities()

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "mid-1"


@pytest.fixture
def chat_id() -> Iterator[str]:
    chat = f"im-{uuid.uuid4().hex[:8]}"
    yield chat
    get_agent_gateway().release_session(chat)
    wake_turn_scheduler._waiting.pop(chat, None)
    get_adaptive_wakeup_service().forget_chat(chat)


@pytest.fixture(autouse=True)
def quiet_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wake_turn_scheduler, "_POLL_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.get_chat_metadata", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr("app.services.chat.chat_service.ChatService.ensure_chat_and_append_user_message", AsyncMock())
    monkeypatch.setattr(service_module, "get_event_bus", lambda: MagicMock())
    monkeypatch.setattr(service_module, "check_estop", lambda: None)
    monkeypatch.setattr(service_module, "should_block_execution", AsyncMock(return_value=False))
    monkeypatch.setattr(service_module, "stream_wake_turn", AsyncMock(return_value=_REPLY))


@pytest.fixture
async def im() -> AsyncIterator[tuple[_Pingchat, WakeOrigins]]:
    channel, origins = _Pingchat(), WakeOrigins()
    gateway = ChannelGateway()
    gateway.register(channel)
    gateway.enable_bidirectional(pairing_store=MagicMock(), agent_executor=MagicMock())
    router = gateway._router
    assert router is not None
    router._attach_web_handoff = AsyncMock(side_effect=lambda result, _msg: result)  # type: ignore[method-assign]
    await gateway.start()
    set_wake_reply_returner(ChannelWakeReplyReturner(gateway, origins))
    yield channel, origins
    set_wake_reply_returner(None)
    await gateway.stop()


def _settlement(chat_id: str) -> WakeupEvent:
    return WakeupEvent(
        source_type=WakeupSourceType.SUBAGENT,
        source_id="task-1",
        session_id=chat_id,
        success=True,
        summary="Subagent 'researcher' completed successfully",
    )


async def _settle() -> None:
    async with asyncio.timeout(5):
        while wake_turn_scheduler._tasks:
            await asyncio.gather(*list(wake_turn_scheduler._tasks))


async def _sent_after_settling(channel: _Pingchat, *, expect_none: bool = False) -> list[OutboundMessage]:
    """What the channel received once the wake turn is over and the outbound queue had a moment to drain."""
    await _settle()
    for _ in range(50 if expect_none else 300):
        if channel.sent:
            break
        await asyncio.sleep(0.01)
    return channel.sent


@pytest.mark.asyncio
async def test_a_chat_started_from_im_gets_the_wake_reply_in_that_conversation(
    chat_id: str, im: tuple[_Pingchat, WakeOrigins]
) -> None:
    channel, origins = im
    origins.remember(chat_id, InboundMessage(channel="pingchat", sender_id="u1", chat_id="room-1", content="research it"))

    await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))

    sent = await _sent_after_settling(channel)
    assert [(message.recipient_id, message.content) for message in sent] == [("room-1", _REPLY)]


@pytest.mark.asyncio
async def test_a_chat_started_in_the_app_keeps_the_wake_reply_in_the_app(chat_id: str, im: tuple[_Pingchat, WakeOrigins]) -> None:
    channel, _origins = im

    await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))

    assert await _sent_after_settling(channel, expect_none=True) == []
