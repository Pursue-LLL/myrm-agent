"""Integration: channel_notify_tool → ChannelNotificationSender → bus.send_tracked."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types.status import ChannelStatus
from app.services.agent.outbound_notify import (
    ChannelNotificationSender,
    NotifyTarget,
    NotifyToolConfig,
    create_channel_notify_tool,
)


@pytest.mark.asyncio
async def test_tool_invoke_propagates_send_tracked_failure() -> None:
    """End-to-end tool path surfaces delivery failure (AB' regression guard)."""
    target = NotifyTarget(channel="telegram", recipient_id="chat_1", label="TG")
    sender = ChannelNotificationSender((target,))
    config = NotifyToolConfig(allowed_targets=(target,), rate_limit_per_session=3, max_body_length=1000)
    tool = create_channel_notify_tool(sender, config)

    mock_channel = MagicMock()
    mock_channel.status = ChannelStatus.RUNNING
    mock_bus = MagicMock()
    mock_bus.channels = {"telegram": mock_channel}
    mock_bus.send_tracked = AsyncMock(return_value=None)

    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus

    mock_channel_bridge = MagicMock()
    mock_channel_bridge.channel_gateway = mock_gateway

    with patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}):
        result = await tool.ainvoke({"channel": "telegram", "target": "chat_1", "body": "done"})

    assert "error" in result.lower()
    assert "delivery failed" in result.lower() or "failed" in result.lower()
    mock_bus.send_tracked.assert_awaited_once()


@pytest.mark.asyncio
async def test_tool_invoke_reports_success_with_message_id() -> None:
    target = NotifyTarget(channel="slack", recipient_id="C1")
    sender = ChannelNotificationSender((target,))
    config = NotifyToolConfig(allowed_targets=(target,))
    tool = create_channel_notify_tool(sender, config)

    mock_channel = MagicMock()
    mock_channel.status = ChannelStatus.RUNNING
    mock_bus = MagicMock()
    mock_bus.channels = {"slack": mock_channel}
    mock_bus.send_tracked = AsyncMock(return_value="plat-msg-42")

    mock_gateway = MagicMock()
    mock_gateway.bus = mock_bus

    mock_channel_bridge = MagicMock()
    mock_channel_bridge.channel_gateway = mock_gateway

    with patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}):
        result = await tool.ainvoke({"channel": "slack", "target": "C1", "body": "Summary ready"})

    assert "success" in result.lower()
    assert "slack" in result.lower()
