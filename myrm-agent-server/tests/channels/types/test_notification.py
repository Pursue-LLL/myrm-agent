"""Tests for channel notification metadata constants and helpers."""

from __future__ import annotations

from app.channels.providers.telegram.notification import (
    notification_kwargs as tg_notification_kwargs,
)
from app.channels.types.messages import MessagePriority, OutboundMessage
from app.channels.types.notification import (
    METADATA_EXPLICIT_MENTION_KEY,
    METADATA_GUEST_TURN_KEY,
    METADATA_NOTIFY_KEY,
    ChannelNotificationMode,
    parse_notification_mode,
    should_notify,
    with_final_notify,
)


def _msg(**kwargs: object) -> OutboundMessage:
    return OutboundMessage(channel="telegram", user_id="u1", recipient_id="1", content="hi", **kwargs)


def test_metadata_keys_are_stable() -> None:
    assert METADATA_NOTIFY_KEY == "notify"
    assert METADATA_GUEST_TURN_KEY == "guest_turn"
    assert METADATA_EXPLICIT_MENTION_KEY == "explicit_mention"


def test_parse_notification_mode_defaults_to_important() -> None:
    assert parse_notification_mode("") == ChannelNotificationMode.IMPORTANT
    assert parse_notification_mode("IMPORTANT") == ChannelNotificationMode.IMPORTANT
    assert parse_notification_mode("all") == ChannelNotificationMode.ALL


def test_should_notify_for_system_and_metadata() -> None:
    assert should_notify(_msg(priority=MessagePriority.SYSTEM)) is True
    tagged = with_final_notify(_msg())
    assert should_notify(tagged) is True


def test_notification_kwargs_builder() -> None:
    assert tg_notification_kwargs(ChannelNotificationMode.IMPORTANT, None) == {
        "disable_notification": True,
    }
    assert tg_notification_kwargs(ChannelNotificationMode.ALL, None) == {}
