from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router_stream import RouterStreamMixin
from app.channels.types import ProgressUpdate
from app.channels.types.messages import InboundMessage, MessagePriority, OutboundMessage
from app.channels.types.status import ChannelCapabilities


@dataclass
class _FakeChannel:
    capabilities: ChannelCapabilities


class DummyRouter(RouterStreamMixin):
    def __init__(self, bus: AsyncMock) -> None:
        self._bus = bus


@pytest.fixture
def mock_bus():
    bus = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


@pytest.fixture
def stream_handler(mock_bus):
    return DummyRouter(mock_bus)


def _make_msg(**overrides: object) -> InboundMessage:
    defaults: dict = dict(
        channel="telegram",
        chat_id="-100123456789",
        sender_id="123",
        content="/test",
        is_group=False,
    )
    defaults.update(overrides)
    return InboundMessage(**defaults)


# ---------------------------------------------------------------------------
# _send_interactive_progress
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_send_interactive_progress_preserves_thread_id(stream_handler, mock_bus):
    msg = _make_msg(
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
    msg = _make_msg()
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


# ---------------------------------------------------------------------------
# _reassurance_loop: edit-in-place heartbeat
# ---------------------------------------------------------------------------

_THRESHOLD_PATH = "app.channels.routing.router_constants._SILENCE_REASSURANCE_THRESHOLD"
_MAX_COUNT_PATH = "app.channels.routing.router_constants._MAX_REASSURANCE_COUNT"
_SHORT_THRESHOLD = 0.05


def _state(last_activity_offset: float = 0.0) -> dict[str, float | int | str]:
    """Create reassurance state with ``last_activity`` set *offset* seconds ago."""
    return {
        "last_activity": time.monotonic() - last_activity_offset,
        "step_count": 3,
        "current_stage": "analyzing",
    }


@pytest.mark.asyncio
async def test_reassurance_sends_first_then_edits(mock_bus):
    """First heartbeat sends a new message; second heartbeat edits it."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-42")
    mock_bus.edit_channel_message = AsyncMock(return_value=True)

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=5.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 2),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        await asyncio.sleep(_SHORT_THRESHOLD * 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_bus.send_tracked.assert_called_once()
    sent_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert sent_msg.priority == MessagePriority.NORMAL

    assert mock_bus.edit_channel_message.call_count >= 1
    edit_args = mock_bus.edit_channel_message.call_args
    assert edit_args[0][0] == "telegram"
    assert edit_args[0][1] == "chat-1"
    assert edit_args[0][2] == "msg-42"


@pytest.mark.asyncio
async def test_reassurance_fallback_when_channel_cannot_edit(mock_bus):
    """When channel doesn't support edit, every heartbeat sends a new message."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=False))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-new")

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=5.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 2),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        await asyncio.sleep(_SHORT_THRESHOLD * 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert mock_bus.send_tracked.call_count >= 2
    mock_bus.edit_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_reassurance_fallback_on_edit_failure(mock_bus):
    """When edit fails, fallback to sending a new message."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-1")
    mock_bus.edit_channel_message = AsyncMock(return_value=False)

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=5.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 2),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        await asyncio.sleep(_SHORT_THRESHOLD * 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert mock_bus.send_tracked.call_count >= 2


@pytest.mark.asyncio
async def test_reassurance_uses_normal_priority(mock_bus):
    """Reassurance messages must use NORMAL priority to avoid push notifications."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=False))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-1")

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=5.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 1),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        await asyncio.sleep(_SHORT_THRESHOLD * 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    sent_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert sent_msg.priority == MessagePriority.NORMAL


@pytest.mark.asyncio
async def test_reassurance_skips_when_activity_recent(mock_bus):
    """Heartbeat skips when last_activity is recent (within threshold)."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=0.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 1),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        state["last_activity"] = time.monotonic()
        await asyncio.sleep(_SHORT_THRESHOLD * 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    mock_bus.send_tracked.assert_not_called()
    mock_bus.edit_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_reassurance_send_tracked_returns_none(mock_bus):
    """When send_tracked returns None, next iteration retries send."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value=None)

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=5.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 2),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        await asyncio.sleep(_SHORT_THRESHOLD * 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert mock_bus.send_tracked.call_count >= 2
    mock_bus.edit_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_reassurance_exception_does_not_crash_loop(mock_bus):
    """Exception in send_tracked does not crash the loop."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=False))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(side_effect=[RuntimeError("network"), "msg-ok"])

    handler = DummyRouter(mock_bus)
    msg = _make_msg()
    state = _state(last_activity_offset=5.0)

    with (
        patch(_THRESHOLD_PATH, _SHORT_THRESHOLD),
        patch(_MAX_COUNT_PATH, 2),
    ):
        task = asyncio.create_task(handler._reassurance_loop(msg, "chat-1", state))
        await asyncio.sleep(_SHORT_THRESHOLD * 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    assert mock_bus.send_tracked.call_count >= 2

