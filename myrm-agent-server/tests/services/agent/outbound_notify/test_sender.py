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
        assert config.destinations == {
            "telegram:My TG": NotifyTarget(channel="telegram", recipient_id="123"),
            "slack#2": NotifyTarget(channel="slack", recipient_id="C456"),
        }


def _destinations(*rows: dict[str, object]) -> list[str]:
    """Destination names offered for these configuration rows (rows come from stored JSON, so values may be any type)."""
    result = create_notification_sender(rows)
    return list(result[1].destinations) if result else []


class TestDestinationNames:
    def test_label_names_the_destination(self) -> None:
        assert _destinations({"channel": "telegram", "recipient_id": "1", "label": "work"}) == ["telegram:work"]

    def test_row_without_label_is_named_by_its_position(self) -> None:
        rows = (
            {"channel": "telegram", "recipient_id": "1", "label": "work"},
            {"channel": "slack", "recipient_id": "C2"},
            {"channel": "slack", "recipient_id": "C3", "label": "  "},
        )
        assert _destinations(*rows) == ["telegram:work", "slack#2", "slack#3"]

    def test_repeated_names_get_a_numeric_suffix(self) -> None:
        rows = (
            {"channel": "telegram", "recipient_id": "1", "label": "work"},
            {"channel": "telegram", "recipient_id": "2", "label": "work"},
            {"channel": "telegram", "recipient_id": "3", "label": "work"},
        )
        assert _destinations(*rows) == ["telegram:work", "telegram:work-2", "telegram:work-3"]

    def test_names_keep_the_order_the_targets_were_configured_in(self) -> None:
        rows = tuple({"channel": "slack", "recipient_id": f"C{i}", "label": f"team {i}"} for i in (3, 1, 2))
        assert _destinations(*rows) == ["slack:team 3", "slack:team 1", "slack:team 2"]

    def test_position_counts_dropped_rows_so_a_name_matches_the_row_the_user_sees(self) -> None:
        rows = (
            {"channel": "telegram", "recipient_id": ""},
            {"channel": "slack", "recipient_id": "C2"},
        )
        assert _destinations(*rows) == ["slack#2"]


class TestTargetNormalization:
    @pytest.mark.parametrize(
        "row",
        [
            {"channel": "telegram"},
            {"recipient_id": "1"},
            {"channel": "", "recipient_id": "1"},
            {"channel": "telegram", "recipient_id": "   "},
            {"channel": None, "recipient_id": "1"},
            {"channel": "telegram", "recipient_id": 42},
        ],
        ids=["no-recipient", "no-channel", "empty-channel", "blank-recipient", "null-channel", "numeric-recipient"],
    )
    def test_row_that_cannot_deliver_is_dropped(self, row: dict[str, object]) -> None:
        valid = {"channel": "slack", "recipient_id": "C9", "label": "ops"}
        assert _destinations(row, valid) == ["slack:ops"]

    def test_every_row_malformed_means_no_tool(self) -> None:
        assert create_notification_sender(({"channel": "telegram"}, {"recipient_id": "1"})) is None

    def test_each_dropped_row_logs_its_position_and_never_the_recipient(self, caplog: pytest.LogCaptureFixture) -> None:
        rows = (
            {"channel": "telegram", "recipient_id": ""},
            {"channel": "slack", "recipient_id": "C-SECRET-9", "label": "ops"},
            {"channel": "", "recipient_id": "chat-SECRET-7"},
        )
        with caplog.at_level("WARNING", logger="app.services.agent.outbound_notify.sender"):
            assert _destinations(*rows) == ["slack:ops"]

        warnings = [record.getMessage() for record in caplog.records]
        assert len(warnings) == 2
        assert "row 1" in warnings[0]
        assert "row 3" in warnings[1]
        assert all("SECRET" not in message for message in warnings)

    @pytest.mark.parametrize(
        ("label", "expected"),
        [
            ("  work  ", "work"),
            ("two\nlines", "two lines"),
            ("tab\tand   spaces", "tab and spaces"),
            ("bell\x07\x1b[31mred", "bell[31mred"),
            ("zero\u200bwidth", "zerowidth"),
            ("x" * 40, "x" * 32),
            ("y" * 31 + " tail", "y" * 31),
        ],
        ids=["strip", "newline", "tabs-and-runs", "control-chars", "format-char", "length-cap", "no-trailing-space-after-cap"],
    )
    def test_label_is_cleaned_for_display(self, label: str, expected: str) -> None:
        assert _destinations({"channel": "telegram", "recipient_id": "1", "label": label}) == [f"telegram:{expected}"]

    def test_label_of_only_control_characters_falls_back_to_the_position(self) -> None:
        assert _destinations({"channel": "telegram", "recipient_id": "1", "label": "\x00\n\t"}) == ["telegram#1"]

    def test_recipient_and_channel_are_stripped(self) -> None:
        result = create_notification_sender(({"channel": " telegram ", "recipient_id": " 42 ", "label": "me"},))
        assert result is not None
        assert result[1].destinations["telegram:me"] == NotifyTarget(channel="telegram", recipient_id="42")


def _bridge_with_send_now(**send_now_kwargs: object) -> MagicMock:
    """Fake ``app.core.channel_bridge`` module exposing a gateway whose bus ``send_now`` is mocked."""
    bridge = MagicMock()
    bridge.channel_gateway.bus.send_now = AsyncMock(**send_now_kwargs)
    return bridge


class TestChannelNotificationSender:
    @pytest.mark.asyncio
    async def test_send_success(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender()
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
        sender = ChannelNotificationSender()
        bridge = _bridge_with_send_now(return_value=None)

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is True
        assert result.message_id == ""

    @pytest.mark.asyncio
    async def test_send_fails_when_gateway_none(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender()

        mock_channel_bridge = MagicMock()
        mock_channel_bridge.channel_gateway = None

        with patch.dict("sys.modules", {"app.core.channel_bridge": mock_channel_bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "not initialized" in result.error

    @pytest.mark.asyncio
    async def test_send_fails_when_channel_not_registered(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender()
        bridge = _bridge_with_send_now(side_effect=ChannelSendError("No channel registered for 'telegram'"))

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "No channel registered" in result.error

    @pytest.mark.asyncio
    async def test_send_reports_delivery_failure_reason(self) -> None:
        target = NotifyTarget(channel="slack", recipient_id="C456")
        sender = ChannelNotificationSender()
        bridge = _bridge_with_send_now(side_effect=ChannelSendError("channel send returned no message_id"))

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert result.error == "channel send returned no message_id"
        assert result.channel == "slack"

    @pytest.mark.asyncio
    async def test_send_fails_when_channel_stopped(self) -> None:
        target = NotifyTarget(channel="slack", recipient_id="C456")
        sender = ChannelNotificationSender()
        bridge = _bridge_with_send_now(side_effect=ChannelSendError("Channel 'slack' is stopped"))

        with patch.dict("sys.modules", {"app.core.channel_bridge": bridge}):
            result = await sender.send(target, "Hello")

        assert result.success is False
        assert "stopped" in result.error.lower()
        assert result.channel == "slack"

    @pytest.mark.asyncio
    async def test_send_handles_unexpected_exception(self) -> None:
        target = NotifyTarget(channel="telegram", recipient_id="123")
        sender = ChannelNotificationSender()

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
