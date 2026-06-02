"""Telegram notification mode helpers."""

from __future__ import annotations

import dataclasses

from app.channels.providers.telegram.notification import notification_kwargs
from app.channels.types import MessagePriority, OutboundMessage
from app.channels.types.notification import (
    METADATA_NOTIFY_KEY,
    ChannelNotificationMode,
    should_notify,
    with_final_notify,
)


def _msg(**kwargs: object) -> OutboundMessage:
    base = {
        "channel": "telegram",
        "recipient_id": "42",
        "content": "hello",
        "user_id": "u1",
    }
    base.update(kwargs)
    return OutboundMessage(**base)  # type: ignore[arg-type]


def test_important_mode_defaults_silent() -> None:
    assert notification_kwargs(ChannelNotificationMode.IMPORTANT, None) == {
        "disable_notification": True,
    }


def test_important_mode_final_reply_rings() -> None:
    final = with_final_notify(_msg())
    assert notification_kwargs(ChannelNotificationMode.IMPORTANT, final) == {}
    assert final.metadata is not None
    assert final.metadata[METADATA_NOTIFY_KEY] is True


def test_system_priority_rings_without_metadata() -> None:
    system = _msg(priority=MessagePriority.SYSTEM)
    assert should_notify(system) is True
    assert notification_kwargs(ChannelNotificationMode.IMPORTANT, system) == {}


def test_all_mode_never_disables() -> None:
    assert notification_kwargs(ChannelNotificationMode.ALL, None) == {}
    assert notification_kwargs(ChannelNotificationMode.ALL, _msg()) == {}


def test_with_final_notify_is_idempotent() -> None:
    already = _msg(metadata={METADATA_NOTIFY_KEY: True})
    assert with_final_notify(already) is already
    tagged = with_final_notify(_msg())
    assert dataclasses.replace(tagged, metadata={METADATA_NOTIFY_KEY: False}) != tagged
