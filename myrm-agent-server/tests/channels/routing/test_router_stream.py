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


@pytest.mark.asyncio
async def test_send_interactive_progress_adds_mobile_status_button(stream_handler, mock_bus):
    msg = InboundMessage(
        channel="telegram",
        chat_id="-100123456789",
        sender_id="123",
        content="/test",
        is_group=False,
    )
    progress = ProgressUpdate(label="Approve tool call?", quick_replies=None)
    deep_link = "https://tunnel.example.com/mobile/status/chat-1?pair=token"

    stream_handler._resolve_mobile_status_deep_link = AsyncMock(return_value=deep_link)

    await stream_handler._send_interactive_progress(msg, "chat-1", progress)

    mock_bus.send_tracked.assert_called_once()
    outbound_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert outbound_msg.components is not None
    assert len(outbound_msg.components) == 1
    button = outbound_msg.components[0][0]
    assert button.action_id == "mobile:open_status"
    assert button.url == deep_link

