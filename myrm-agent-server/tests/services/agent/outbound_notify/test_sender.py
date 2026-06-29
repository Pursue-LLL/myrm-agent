"""Tests for ChannelNotificationSender and create_notification_sender."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

        mock_gateway = AsyncMock()
        mock_gateway.publish = AsyncMock()

        mock_channel_bridge = MagicMock()
        mock_channel_bridge.channel_gateway = mock_gateway

        with (
            patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}),
            patch("app.channels.types.OutboundMessage") as mock_msg_cls,
            patch("app.channels.types.messages.MessagePriority") as _mock_priority,
        ):
            mock_msg_cls.return_value = MagicMock()
            result = await sender.send(target, "Hello world")

        assert result.success is True
        assert result.channel == "telegram"
        assert result.error == ""

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
    async def test_send_handles_publish_error(self) -> None:
        target = NotifyTarget(channel="slack", recipient_id="C456")
        sender = ChannelNotificationSender((target,))

        mock_gateway = AsyncMock()
        mock_gateway.publish = AsyncMock(side_effect=RuntimeError("network error"))

        mock_channel_bridge = MagicMock()
        mock_channel_bridge.channel_gateway = mock_gateway

        with (
            patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}),
            patch("app.channels.types.OutboundMessage") as mock_msg_cls,
            patch("app.channels.types.messages.MessagePriority"),
        ):
            mock_msg_cls.return_value = MagicMock()
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "network error" in result.error
        assert result.channel == "slack"
