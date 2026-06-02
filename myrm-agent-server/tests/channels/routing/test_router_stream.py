from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.router_stream import RouterStreamMixin
from app.channels.types import ProgressUpdate
from app.channels.types.messages import InboundMessage, OutboundMessage


class DummyRouter(RouterStreamMixin):
    def __init__(self, bus):
        self._bus = bus


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


@pytest.fixture
def stream_handler(mock_bus):
    handler = DummyRouter(mock_bus)
    return handler


@pytest.mark.asyncio
async def test_send_interactive_progress_preserves_thread_id(stream_handler, mock_bus):
    msg = InboundMessage(
        channel="telegram",
        chat_id="-100123456789",
        sender_id="123",
        content="/test",
        is_group=True,
        thread_id="456",
        message_id="789",
        metadata={"message_id": "789"},
    )
    progress = ProgressUpdate(label="Working...", quick_replies=None)

    await stream_handler._send_interactive_progress(msg, "-100123456789", progress)

    mock_bus.send_tracked.assert_called_once()
    outbound_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]

    assert outbound_msg.thread_id == "456"
    assert outbound_msg.reply_to_id == "789"
    assert outbound_msg.content == "Working..."
