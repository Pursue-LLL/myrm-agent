"""A gateway shutdown delivers what the router published while stopping, even over a channel that takes time to send.

The notice a delegated task sends when the service stops is queued by ``AgentRouter.stop()``; the gateway then closes
the channels. Without waiting for the outbound queue in between, any channel with a real send latency loses it.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.delegation import DelegationStatus
from app.channels.i18n import get_text
from app.channels.types import ChannelCapabilities, InboundMessage, OutboundMessage, StreamingText

_REQUEST = InboundMessage(channel="slow", sender_id="u1", chat_id="c1", content="/delegate x", metadata={"locale": "en"})


class _SlowChannel(BaseChannel):
    """A provider whose send takes real time, like a platform API call."""

    name = "slow"
    capabilities = ChannelCapabilities()

    def __init__(self, latency: float) -> None:
        super().__init__()
        self._latency = latency
        self.delivered: list[str] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        await asyncio.sleep(self._latency)
        self.delivered.append(msg.content)
        return "mid-1"


async def _hang(*_args: object, **_kwargs: object) -> AsyncGenerator[object, None]:
    yield StreamingText(text="working")
    await asyncio.Event().wait()


async def _gateway_with_running_task(channel: BaseChannel) -> tuple[ChannelGateway, str]:
    gateway = ChannelGateway()
    gateway.register(channel)
    executor = MagicMock()
    executor.execute_stream = _hang
    gateway.enable_bidirectional(pairing_store=MagicMock(), agent_executor=executor)
    await gateway.start()
    router = gateway._router
    assert router is not None
    router._resolve_mobile_status_deep_link = AsyncMock(return_value=None)  # type: ignore[method-assign]
    await router._handle_delegation_inbound(_REQUEST, "x")
    coordinator = router.delegation_coordinator
    for _ in range(300):
        running = [t.task_id for t in coordinator._tasks.values() if t.status is DelegationStatus.RUNNING]
        if running:
            return gateway, running[0]
        await asyncio.sleep(0.01)
    raise AssertionError("the delegated task never started")


@pytest.mark.asyncio
@pytest.mark.parametrize("latency", [0.0, 0.3])
async def test_the_interruption_notice_is_delivered_before_the_channels_close(latency: float) -> None:
    channel = _SlowChannel(latency)
    gateway, task_id = await _gateway_with_running_task(channel)
    await asyncio.sleep(latency + 0.2)  # the receipt goes out first

    await gateway.stop()

    assert get_text(_REQUEST, "delegation_interrupted", task_id=task_id) in channel.delivered
