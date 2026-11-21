"""ChannelGateway-backed outbound notification sender.

[INPUT]
- app.channels.core.gateway::ChannelGateway (POS: multi-platform channel gateway)
- app.channels.types::OutboundMessage (POS: outbound message model)
- app.channels.types.messages::MediaAttachment (POS: media attachment model)
- .types::NotifyResult, NotifyTarget, NotifyToolConfig (POS: outbound notification data types)

[OUTPUT]
- ChannelNotificationSender: NotificationSender implementation via ChannelGateway bus send_now.
- create_notification_sender: Factory from agent notify_targets; names each usable row as a destination.

[POS]
Channel delivery for agent-initiated outbound notifications, and the normalization of the configured targets into the
closed destination set the tool offers.
"""

from __future__ import annotations

import logging
import unicodedata
from typing import TYPE_CHECKING

from .constants import METADATA_KEY_NOTIFY_SOURCE, NOTIFY_SOURCE_AGENT
from .types import NotifyResult, NotifyTarget, NotifyToolConfig

if TYPE_CHECKING:
    from app.channels.types.messages import MediaAttachment

logger = logging.getLogger(__name__)

_MAX_LABEL_CHARS = 32


class ChannelNotificationSender:
    """Sends notifications via ChannelGateway bus send_now (synchronous delivery result)."""

    async def send(
        self,
        target: NotifyTarget,
        body: str,
        media: tuple[MediaAttachment, ...] = (),
    ) -> NotifyResult:
        """Deliver notification via ChannelGateway bus (always NORMAL priority)."""
        try:
            from app.channels.types import OutboundMessage
            from app.channels.types.messages import MessagePriority
            from app.core.channel_bridge import channel_gateway

            if channel_gateway is None:
                return NotifyResult(
                    success=False,
                    channel=target.channel,
                    error="Channel gateway not initialized",
                )

            msg = OutboundMessage(
                channel=target.channel,
                recipient_id=target.recipient_id,
                content=body,
                user_id="system",
                priority=MessagePriority.NORMAL,
                media=media,
                metadata={METADATA_KEY_NOTIFY_SOURCE: NOTIFY_SOURCE_AGENT},
            )
            message_id = await channel_gateway.bus.send_now(msg)

            logger.info(
                "Notification sent: channel=%s, recipient=%s, len=%d, media=%d, message_id=%s",
                target.channel,
                target.recipient_id,
                len(body),
                len(media),
                message_id,
            )
            return NotifyResult(
                success=True,
                channel=target.channel,
                message_id=message_id or "",
            )
        except Exception as exc:
            logger.warning(
                "Notification delivery failed: channel=%s, recipient=%s, error=%s",
                target.channel,
                target.recipient_id,
                exc,
            )
            return NotifyResult(
                success=False,
                channel=target.channel,
                error=str(exc),
            )


def _text(value: object) -> str:
    """The stripped string, or an empty string for anything that is not text."""
    return value.strip() if isinstance(value, str) else ""


def _clean_label(value: object) -> str:
    """A label the approver and the model can read: no control characters, single spaces, bounded length.

    Labels come from pairing display names, which the other party controls, so this keeps them tidy; it does not make
    them trustworthy, and every send still needs the user's approval.
    """
    if not isinstance(value, str):
        return ""
    # Any whitespace (newlines included) becomes one space; other control and format characters are dropped.
    kept = (" " if ch.isspace() else ch for ch in value if ch.isspace() or not unicodedata.category(ch).startswith("C"))
    return " ".join("".join(kept).split())[:_MAX_LABEL_CHARS].rstrip()


def _build_destinations(raw_targets: tuple[dict[str, str], ...]) -> dict[str, NotifyTarget]:
    """Name each usable configured target; a row without a channel or a recipient cannot deliver and is skipped.

    A name is ``channel:label``; a row without a label is named by its position in the configuration
    (``channel#2`` is the second row), and a repeated name gets ``-2``, ``-3`` appended.
    """
    destinations: dict[str, NotifyTarget] = {}
    for position, row in enumerate(raw_targets, start=1):
        channel = _text(row.get("channel"))
        recipient_id = _text(row.get("recipient_id"))
        if not channel or not recipient_id:
            logger.warning("Skipped notify_targets row %d: channel and recipient_id are required", position)
            continue
        label = _clean_label(row.get("label"))
        base = f"{channel}:{label}" if label else f"{channel}#{position}"
        destination, suffix = base, 2
        while destination in destinations:
            destination, suffix = f"{base}-{suffix}", suffix + 1
        destinations[destination] = NotifyTarget(channel=channel, recipient_id=recipient_id)
    return destinations


def create_notification_sender(
    raw_targets: tuple[dict[str, str], ...],
) -> tuple[ChannelNotificationSender, NotifyToolConfig] | None:
    """Create sender + config from agent profile notify_targets.

    Returns None when no row is usable (tool won't be registered).
    """
    destinations = _build_destinations(raw_targets)
    if not destinations:
        return None
    return ChannelNotificationSender(), NotifyToolConfig(destinations=destinations)
