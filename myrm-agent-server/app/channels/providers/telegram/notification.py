"""Telegram ``disable_notification`` helpers: ``all`` notifies for every message, ``important`` silences the rest."""

from __future__ import annotations

from typing import TypedDict

from app.channels.types.messages import OutboundMessage
from app.channels.types.notification import (
    ChannelNotificationMode,
    should_notify,
)


class NotificationKwargs(TypedDict, total=False):
    """Keyword arguments of a Telegram send call that control the push notification."""

    disable_notification: bool


def notification_kwargs(
    mode: ChannelNotificationMode,
    msg: OutboundMessage | None = None,
) -> NotificationKwargs:
    """Build Telegram API kwargs for ``disable_notification``."""
    if mode == ChannelNotificationMode.ALL:
        return {}
    if should_notify(msg):
        return {}
    return {"disable_notification": True}
