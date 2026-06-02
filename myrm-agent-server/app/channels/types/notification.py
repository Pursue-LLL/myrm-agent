"""Channel notification mode types and outbound notify metadata constants."""

from __future__ import annotations

import dataclasses
from enum import StrEnum

from app.channels.types.messages import MessagePriority, OutboundMessage

METADATA_NOTIFY_KEY = "notify"
METADATA_EXPLICIT_MENTION_KEY = "explicit_mention"
METADATA_GUEST_TURN_KEY = "guest_turn"


class ChannelNotificationMode(StrEnum):
    """Outbound push notification policy for a channel provider.

    IMPORTANT: suppress progress/placeholder noise; final replies ring when
    ``metadata[METADATA_NOTIFY_KEY]`` is set or ``MessagePriority.SYSTEM``.
    ALL: every outbound message may trigger a push notification (legacy).
    """

    IMPORTANT = "important"
    ALL = "all"


def parse_notification_mode(raw: str) -> ChannelNotificationMode:
    """Parse credential/config string to ``ChannelNotificationMode``."""
    normalized = raw.strip().lower()
    if normalized == ChannelNotificationMode.ALL:
        return ChannelNotificationMode.ALL
    return ChannelNotificationMode.IMPORTANT


def should_notify(msg: OutboundMessage | None) -> bool:
    """Return True when an outbound message should trigger a push notification."""
    if msg is None:
        return False
    if msg.priority == MessagePriority.SYSTEM:
        return True
    meta = msg.metadata or {}
    return bool(meta.get(METADATA_NOTIFY_KEY))


def with_final_notify(msg: OutboundMessage) -> OutboundMessage:
    """Mark a final agent reply so it rings in IMPORTANT notification mode."""
    if should_notify(msg):
        return msg
    meta = dict(msg.metadata or {})
    meta[METADATA_NOTIFY_KEY] = True
    return dataclasses.replace(msg, metadata=meta)
