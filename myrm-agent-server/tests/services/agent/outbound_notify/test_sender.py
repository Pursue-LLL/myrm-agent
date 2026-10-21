"""Tests for ChannelNotificationSender and create_notification_sender."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.exceptions import ChannelSendError
from app.services.agent.outbound_notify import (
    ChannelNotificationSender,
    NotifyTarget,
    create_notification_sender,
)


class TestCreateNotificationSender:
    def test_returns_none_for_empty_targets(self) -> None:
        assert create_notification_sender(()) is None

    def test_returns_sender_and_config(self) -> None:
        raw = (
            {"channel": "telegram", "recipient_id": "123", "label": "My TG"},
            {"channel": "slack", "recipient_id": "C456"},
        )
        result = create_notification_sender(raw)
        assert result is not None

        sender, config = result
        assert isinstance(sender, ChannelNotificationSender)
        assert config.rate_limit_per_session == 10
        assert config.max_body_length == 4000
        assert len(config.allowed_targets) == 2
        assert config.allowed_targets[0].channel == "telegram"
        assert config.allowed_targets[0].label == "My TG"
        assert config.allowed_targets[1].channel == "slack"
        assert config.allowed_targets[1].label == ""


def _bridge_with_send_now(**send_now_kwargs: object) -> MagicMock:
    """Fake ``app.core.channel_bridge`` module exposing a gateway whose bus ``send_now`` is mocked."""
    bridge = MagicMock()
    bridge.channel_gateway.bus.send_now = AsyncMock(**send_now_kwargs)
    return bridge


class TestChannelNotificationSender:
    @pytest.mark.asyncio
    async def test_list_available_targets(self) -> None:
        targets = (
            NotifyTarget(channel="telegram", recipient_id="123"),
            NotifyTarget(channel="slack", recipient_id="C456"),
        )
        sender = ChannelNotificationSender(targets)
        result = await sender.list_available_targets()
        assert len(result) == 2
        assert result[0].channel == "telegram"

    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender((target,))
        bridge = _bridge_with_send_now(return_value="msg-abc")

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello world")

        assert result.success is True
        assert result.channel == "telegram"
        assert result.message_id == "msg-abc"
        assert result.error == ""
        bridge.channel_gateway.bus.send_now.assert_awaited_once()
        sent = bridge.channel_gateway.bus.send_now.call_args[0][0]
        assert (sent.channel, sent.recipient_id, sent.content) == ("telegram", "123", "Hello world")

    @pytest.mark.asyncio
    async def test_send_success_without_platform_message_id(self) -> None:
        """Channels that report no ids (e.g. DingTalk) still count as delivered."""
        target = NotifyTarget(channel="dingtalk", recipient_id="u1")
        sender = ChannelNotificationSender((target,))
        bridge = _bridge_with_send_now(return_value=None)

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is True
        assert result.message_id == ""

    @pytest.mark.asyncio
    async def test_send_fails_when_gateway_none(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender((target,))

        mock_channel_bridge = MagicMock()
        mock_channel_bridge.channel_gateway = None

        with patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_send_fails_when_channel_not_registered(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender((target,))
        bridge = _bridge_with_send_now(side_effect=ChannelSendError("No channel registered for 'telegram'"))

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "No channel registered" in result.error

    @pytest.mark.asyncio
    async def test_send_reports_delivery_failure_reason(self) -> None:
        target = NotifyTarget(channel="slack", recipient_id="C456")
        sender = ChannelNotificationSender((target,))
        bridge = _bridge_with_send_now(side_effect=ChannelSendError("channel send returned no message_id"))

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert result.error == "channel send returned no message_id"
        assert result.channel == "slack"

    @pytest.mark.asyncio
    async def test_send_fails_when_channel_stopped(self) -> None:
        target = NotifyTarget(channel="slack", recipient_id="C456")
        sender = ChannelNotificationSender((target,))
        bridge = _bridge_with_send_now(side_effect=ChannelSendError("Channel 'slack' is stopped"))

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "stopped" in result.error.lower()
        assert result.channel == "slack"

    @pytest.mark.asyncio
    async def test_send_handles_unexpected_exception(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender((target,))

        mock_channel_bridge = MagicMock()
        mock_channel_bridge.channel_gateway = MagicMock()

        with (
            patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}),
            patch("app.channels.types.OutboundMessage", side_effect=RuntimeError("boom")),
        ):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert result.error == "boom"
        assert result.channel == "telegram"
