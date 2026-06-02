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
def message_bus(tmp_path):
    return MessageBus(dlq_dir=tmp_path / "dlq")


@pytest.fixture
def dummy_channel():
    return DummyChannel()


@pytest.mark.asyncio
async def test_message_bus_dlq_on_failure(message_bus, dummy_channel):
    message_bus.register_channel(dummy_channel)

    # Make send fail
    dummy_channel.send_mock.side_effect = Exception("Simulated send failure")

    msg = OutboundMessage(channel="dummy", recipient_id="user1", content="test message", user_id="user1")

    await message_bus.start()

    # Publish message, it should fail and go to DLQ
    await message_bus.publish_outbound(msg)

    # Wait a bit for dispatch loop to process
    await asyncio.sleep(0.1)

    # Check DLQ
    dlq_msgs = await message_bus.get_dlq_messages()
    assert len(dlq_msgs) == 1

    # Get the actual message object from DLQ
    dlq_msg = dlq_msgs[0]

    assert dlq_msg.channel == "dummy"
    assert dlq_msg.recipient == "user1"
    assert dlq_msg.content["content"] == "test message"
    assert dummy_channel.send_mock.call_count > 0

    await message_bus.stop()
