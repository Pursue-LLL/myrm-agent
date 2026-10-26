"""Tests for the silence heartbeat: edit-in-place reassurance while a long agent run is quiet."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.routing.router_reassurance import run_reassurance_loop
from app.channels.types.messages import InboundMessage, MessagePriority, OutboundMessage
from app.channels.types.status import ChannelCapabilities

_REASSURANCE_MOD = "app.channels.routing.router_reassurance"
_real_sleep = asyncio.sleep


@dataclass
class _FakeChannel:
    capabilities: ChannelCapabilities


@pytest.fixture
def mock_bus() -> AsyncMock:
    bus = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)
    return bus


_MSG = InboundMessage(channel="telegram", chat_id="-100123456789", sender_id="123", content="/test", is_group=False)


# ---------------------------------------------------------------------------
# run_reassurance_loop: edit-in-place heartbeat
#
# Strategy: use short threshold (0.15s) and max_count=2, real asyncio.sleep
# with state["last_activity"] set far in the past so elapsed always exceeds
# threshold. Tests run in < 1s.
# ---------------------------------------------------------------------------

_SHORT = 0.15


def _stale_state() -> dict[str, float | int | str]:
    """State where last_activity is far in the past (always triggers heartbeat)."""
    return {
        "last_activity": 0.0,
        "step_count": 3,
        "current_stage": "analyzing",
    }


@pytest.mark.asyncio
async def test_reassurance_sends_first_then_edits(mock_bus: AsyncMock) -> None:
    """First heartbeat sends a new message; second heartbeat edits it."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-42")
    mock_bus.edit_channel_message = AsyncMock(return_value=True)

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 2),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    mock_bus.send_tracked.assert_called_once()
    sent_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert sent_msg.priority == MessagePriority.NORMAL

    assert mock_bus.edit_channel_message.call_count == 1
    edit_args = mock_bus.edit_channel_message.call_args
    assert edit_args[0][0] == "telegram"
    assert edit_args[0][1] == "chat-1"
    assert edit_args[0][2] == "msg-42"


@pytest.mark.asyncio
async def test_reassurance_sends_once_when_channel_cannot_edit(mock_bus: AsyncMock) -> None:
    """When channel doesn't support edit, only one heartbeat message is sent.

    After the first send heartbeat_mid is set but can_edit=False, so
    subsequent iterations neither edit nor re-send — preventing message spam
    on channels without edit capability.
    """
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=False))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-new")

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 2),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    mock_bus.send_tracked.assert_called_once()
    mock_bus.edit_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_reassurance_fallback_on_edit_failure(mock_bus: AsyncMock) -> None:
    """When edit fails, heartbeat_mid resets and next iteration sends a new message."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-1")
    mock_bus.edit_channel_message = AsyncMock(return_value=False)

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 2),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    assert mock_bus.send_tracked.call_count == 2


@pytest.mark.asyncio
async def test_reassurance_uses_normal_priority(mock_bus: AsyncMock) -> None:
    """Reassurance messages must use NORMAL priority to avoid push notifications."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=False))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value="msg-1")

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 1),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    sent_msg: OutboundMessage = mock_bus.send_tracked.call_args[0][0]
    assert sent_msg.priority == MessagePriority.NORMAL


@pytest.mark.asyncio
async def test_reassurance_skips_when_activity_recent(mock_bus: AsyncMock) -> None:
    """Heartbeat skips sending when last_activity is within threshold."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)

    msg = _MSG
    state: dict[str, float | int | str] = {
        "last_activity": time.monotonic() + 9999,
        "step_count": 0,
        "current_stage": "",
    }

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 1),
    ):
        task = asyncio.create_task(run_reassurance_loop(mock_bus, msg, "chat-1", state))
        await _real_sleep(_SHORT + 0.1)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    mock_bus.send_tracked.assert_not_called()
    mock_bus.edit_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_reassurance_send_tracked_returns_none(mock_bus: AsyncMock) -> None:
    """When send_tracked returns None, heartbeat_mid stays None and retries send."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=True))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(return_value=None)

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 2),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    assert mock_bus.send_tracked.call_count == 2
    mock_bus.edit_channel_message.assert_not_called()


@pytest.mark.asyncio
async def test_reassurance_exception_does_not_crash_loop(mock_bus: AsyncMock) -> None:
    """Exception in send_tracked does not crash the loop; next iteration retries."""
    channel_obj = _FakeChannel(capabilities=ChannelCapabilities(edit=False))
    mock_bus.get_channel = MagicMock(return_value=channel_obj)
    mock_bus.send_tracked = AsyncMock(side_effect=[RuntimeError("network"), "msg-ok"])

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 2),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    assert mock_bus.send_tracked.call_count == 2


@pytest.mark.asyncio
async def test_reassurance_no_channel_sends_once(mock_bus: AsyncMock) -> None:
    """When get_channel returns None, can_edit is False — sends once, never edits."""
    mock_bus.get_channel = MagicMock(return_value=None)
    mock_bus.send_tracked = AsyncMock(return_value="msg-1")

    msg = _MSG
    state = _stale_state()

    with (
        patch(f"{_REASSURANCE_MOD}._SILENCE_REASSURANCE_THRESHOLD", _SHORT),
        patch(f"{_REASSURANCE_MOD}._MAX_REASSURANCE_COUNT", 2),
    ):
        await run_reassurance_loop(mock_bus, msg, "chat-1", state)

    mock_bus.send_tracked.assert_called_once()
    mock_bus.edit_channel_message.assert_not_called()
