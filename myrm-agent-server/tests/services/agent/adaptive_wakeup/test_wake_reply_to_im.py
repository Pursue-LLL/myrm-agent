"""A wake turn waits for the member's turn in an IM chat, and what it says reaches that chat, from the settlement to the channel.

The real service, scheduler, carrier, probe, gateway, router session gate and bus; the stand-ins are the chat store, the
budget, the event bus, the turn the wake would stream (it needs a model), the member's own turn (it needs a model; it
holds the session gate until the test ends it) and the channel (it needs a platform).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupEvent, WakeupSourceType
from myrm_agent_harness.agent.meta_tools.spawn_subagent.agent_manage_tool import create_subagent_control_tool
from myrm_agent_harness.agent.sub_agents.types import SubAgentStatus
from myrm_agent_harness.utils.runtime.wakeup_registry import set_global_wakeup_handler

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.routing.session_gate import SessionGateConfig
from app.channels.types import ChannelCapabilities, InboundMessage, OutboundMessage
from app.core.channel_bridge.agent_executor import deliverable
from app.core.channel_bridge.wake_return import ChannelChatBusyProbe, ChannelWakeReplyReturner, WakeOrigins
from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service, wake_turn_scheduler
from app.services.agent.adaptive_wakeup import service as service_module
from app.services.agent.adaptive_wakeup.chat_busy import set_chat_busy_probe
from app.services.agent.adaptive_wakeup.reply_return import set_wake_reply_returner
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.params.workspace_resolve import chat_session_id
from app.services.agent.wakeup_handler import ServerWakeupHandler

_REPLY = "The research is done: three sources agree."
_MEMBER_MESSAGE = InboundMessage(channel="pingchat", sender_id="u1", chat_id="room-1", content="research it")


class _Pingchat(BaseChannel):
    """An IM platform that records what the bot said."""

    name = "pingchat"
    capabilities = ChannelCapabilities(media=True, file_upload=True)

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
    # No chat has a workspace unless a test gives it one: the lookup is a database read.
    monkeypatch.setattr(deliverable, "resolve_chat_workspace_root", AsyncMock(return_value=None))


@pytest.fixture(autouse=True)
def streamed(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """The turn a wake would stream (it needs a model): it says ``_REPLY``."""
    stream = AsyncMock(return_value=_REPLY)
    monkeypatch.setattr(service_module, "stream_wake_turn", stream)
    return stream


@dataclass
class _Im:
    """The IM side of the app under test: the platform, the chats a member has talked in, and the member's own turn."""

    channel: _Pingchat
    origins: WakeOrigins
    gateway: ChannelGateway
    turn_may_end: asyncio.Event

    def member_starts_a_turn(self, chat_id: str, msg: InboundMessage) -> None:
        """The member talks in ``chat_id``: the router session gate runs a turn for ``msg`` until ``end_the_turn``."""
        self.origins.remember(chat_id, msg)
        assert self.gateway._router is not None
        self.gateway._router._gate.submit(msg)

    def end_the_turn(self) -> None:
        self.turn_may_end.set()


@pytest.fixture
async def im(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_Im]:
    channel, origins, turn_may_end = _Pingchat(), WakeOrigins(), asyncio.Event()
    gateway = ChannelGateway()
    gateway.register(channel)
    gateway.enable_bidirectional(pairing_store=MagicMock(), agent_executor=MagicMock())
    router = gateway._router
    assert router is not None
    router._attach_web_handoff = AsyncMock(side_effect=lambda result, _msg: result)  # type: ignore[method-assign]

    async def member_turn(_msg: InboundMessage) -> None:
        await turn_may_end.wait()

    monkeypatch.setattr(router._gate, "_config", SessionGateConfig(debounce_window_ms=0))
    monkeypatch.setattr(router._gate, "_on_ready", member_turn)
    await gateway.start()
    set_wake_reply_returner(ChannelWakeReplyReturner(gateway, origins))
    set_chat_busy_probe(ChannelChatBusyProbe(gateway, origins))
    yield _Im(channel, origins, gateway, turn_may_end)
    turn_may_end.set()
    set_wake_reply_returner(None)
    set_chat_busy_probe(None)
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
async def test_a_chat_started_from_im_gets_the_wake_reply_in_that_conversation(chat_id: str, im: _Im) -> None:
    im.origins.remember(chat_id, _MEMBER_MESSAGE)

    await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))

    sent = await _sent_after_settling(im.channel)
    assert [(message.recipient_id, message.content) for message in sent] == [("room-1", _REPLY)]


@pytest.mark.asyncio
async def test_a_chat_started_in_the_app_keeps_the_wake_reply_in_the_app(chat_id: str, im: _Im) -> None:
    await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))

    assert await _sent_after_settling(im.channel, expect_none=True) == []


@pytest.mark.asyncio
async def test_a_wake_waits_for_the_member_turn_in_the_chat_and_then_replies(chat_id: str, im: _Im, streamed: AsyncMock) -> None:
    im.member_starts_a_turn(chat_id, _MEMBER_MESSAGE)
    # The member's turn is the router's: the agent gateway sees nothing running.
    assert not get_agent_gateway().is_session_active(chat_id)

    await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))
    await asyncio.sleep(0.15)

    streamed.assert_not_awaited()
    assert im.channel.sent == []

    im.end_the_turn()

    sent = await _sent_after_settling(im.channel)
    assert [(message.recipient_id, message.content) for message in sent] == [("room-1", _REPLY)]


@pytest.mark.asyncio
async def test_the_result_the_member_turn_read_is_not_said_again_after_it(chat_id: str, im: _Im, streamed: AsyncMock) -> None:
    """The member asks, the agent starts a subagent and lists it while it finishes: the answer is that turn's, once."""
    parent = MagicMock()
    parent.list_children.return_value = [{"task_id": "task-1", "status": SubAgentStatus.COMPLETED.value, "result": "found it"}]
    parent._last_context = {"session_id": chat_session_id(chat_id)}
    set_global_wakeup_handler(ServerWakeupHandler())
    try:
        im.member_starts_a_turn(chat_id, _MEMBER_MESSAGE)
        await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))

        await create_subagent_control_tool(parent).ainvoke({"action": "list"})
        im.end_the_turn()
        await _settle()
    finally:
        set_global_wakeup_handler(None)

    streamed.assert_not_awaited()
    assert await _sent_after_settling(im.channel, expect_none=True) == []


@pytest.mark.asyncio
async def test_a_file_the_wake_reply_names_reaches_the_chat_as_an_attachment(
    chat_id: str, im: _Im, streamed: AsyncMock, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "report.pdf").write_bytes(b"%PDF-1.4 findings")
    monkeypatch.setattr(deliverable, "resolve_chat_workspace_root", AsyncMock(return_value=str(tmp_path)))
    streamed.return_value = "The research is done, the report is report.pdf."
    im.origins.remember(chat_id, _MEMBER_MESSAGE)

    await get_adaptive_wakeup_service().handle_settlement(_settlement(chat_id))

    (sent,) = await _sent_after_settling(im.channel)
    assert [attachment.filename for attachment in sent.media] == ["report.pdf"]
    assert "report.pdf" not in sent.content
