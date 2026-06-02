"""Telegram disable_notification helpers (Hermes-compatible important/all modes)."""

from __future__ import annotations

from app.channels.types.messages import OutboundMessage
from app.channels.types.notification import (
    ChannelNotificationMode,
    should_notify,
)


def notification_kwargs(
    mode: ChannelNotificationMode,
    msg: OutboundMessage | None = None,
) -> dict[str, bool]:
    """Build Telegram API kwargs for ``disable_notification``."""
    if mode == ChannelNotificationMode.ALL:
        return {}
    if should_notify(msg):
        return {}
    return {"disable_notification": True}
