import asyncio
from unittest.mock import AsyncMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.types import ChannelCapabilities, ChannelStatus, OutboundMessage


class DummyChannel(BaseChannel):
    name = "dummy"

    def __init__(self):
        super().__init__()
        self.capabilities = ChannelCapabilities()
        self.send_mock = AsyncMock()
        self._status = ChannelStatus.RUNNING

    async def send(self, msg: OutboundMessage) -> str | None:
        return await self.send_mock(msg)


@pytest.fixture
def dummy_channel():
    return DummyChannel()


@pytest.mark.asyncio
async def test_dlq_threshold_exceeded_event_with_cooldown(tmp_path, dummy_channel):
    # Create a MessageBus with a tiny DLQ alert threshold (mocked) and a 1-second cooldown
    bus = MessageBus(dlq_dir=tmp_path / "dlq", dlq_alert_cooldown_sec=1)
    bus.register_channel(dummy_channel)

    # Track emitted events
    emitted_events = []

    def on_alert(name, data):
        emitted_events.append(data)

    bus.events.on("DLQ_THRESHOLD_EXCEEDED", on_alert)

    # Mock DLQ to always return 100 failed count (threshold)
    await bus.start()

    # We need to mock get_failed_count after start() because start() initializes _dlq
    bus._dlq.get_failed_count = AsyncMock(return_value=100)

    # Make send fail
    dummy_channel.send_mock.side_effect = Exception("Simulated send failure")

    msg1 = OutboundMessage(channel="dummy", recipient_id="user1", content="msg1", user_id="u1")
    msg2 = OutboundMessage(channel="dummy", recipient_id="user1", content="msg2", user_id="u1")

    # 1. Publish first message -> fails -> goes to DLQ -> triggers alert
    await bus.publish_outbound(msg1)
    await asyncio.sleep(0.1)  # wait for dispatch

    assert len(emitted_events) == 1
    assert emitted_events[0]["count"] == 100
    assert emitted_events[0]["channel"] == "dummy"

    # 2. Publish second message immediately -> fails -> goes to DLQ -> NO alert (cooldown)
    await bus.publish_outbound(msg2)
    await asyncio.sleep(0.1)

    assert len(emitted_events) == 1  # Still 1

    # 3. Wait for cooldown to expire
    await asyncio.sleep(1.1)

    # 4. Publish third message -> fails -> goes to DLQ -> triggers alert again
    msg3 = OutboundMessage(channel="dummy", recipient_id="user1", content="msg3", user_id="u1")
    await bus.publish_outbound(msg3)
    await asyncio.sleep(0.1)

    assert len(emitted_events) == 2

    await bus.stop()
