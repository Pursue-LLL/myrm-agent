"""ChannelGateway-backed outbound notification sender.

[INPUT]
- app.channels.core.gateway::ChannelGateway (POS: multi-platform channel gateway)
- app.channels.types::OutboundMessage (POS: outbound message model)
- app.channels.types.messages::MediaAttachment (POS: media attachment model)
- .types::NotifyResult, NotifyTarget, NotifyToolConfig (POS: outbound notification data types)

[OUTPUT]
- ChannelNotificationSender: NotificationSender implementation via ChannelGateway bus send_tracked.
- create_notification_sender: Factory from agent notify_targets.

[POS]
Channel delivery for agent-initiated outbound notifications.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from .types import NotifyResult, NotifyTarget, NotifyToolConfig

if TYPE_CHECKING:
    from app.channels.types.messages import MediaAttachment

logger = logging.getLogger(__name__)


class ChannelNotificationSender:
    """Sends notifications via ChannelGateway bus send_tracked (synchronous delivery result)."""

    __slots__ = ("_targets",)

    def __init__(self, targets: tuple[NotifyTarget, ...]) -> None:
        self._targets = targets

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
            from app.channels.types.status import ChannelStatus
            from app.core.channel_bridge import channel_gateway

            if channel_gateway is None:
                return NotifyResult(
                    success=False,
                    channel=target.channel,
                    error="Channel gateway not initialized",
                )

            channel = channel_gateway.bus.channels.get(target.channel)
            if channel is None:
                return NotifyResult(
                    success=False,
                    channel=target.channel,
                    error=f"No channel registered for '{target.channel}'",
                )
            if channel.status in (ChannelStatus.DISABLED, ChannelStatus.STOPPED):
                return NotifyResult(
                    success=False,
                    channel=target.channel,
                    error=f"Channel '{target.channel}' is {channel.status.value}",
                )

            msg = OutboundMessage(
                channel=target.channel,
                recipient_id=target.recipient_id,
                content=body,
                user_id="system",
                priority=MessagePriority.NORMAL,
                media=media,
            )
            message_id = await channel_gateway.bus.send_tracked(msg)
            if message_id is None:
                return NotifyResult(
                    success=False,
                    channel=target.channel,
                    error="Channel delivery failed after retries",
                )

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
                message_id=message_id,
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

    async def list_available_targets(self) -> list[NotifyTarget]:
        """Return configured targets."""
        return list(self._targets)


def create_notification_sender(
    raw_targets: tuple[dict[str, str], ...],
) -> tuple[ChannelNotificationSender, NotifyToolConfig] | None:
    """Create sender + config from agent profile notify_targets.

    Returns None if no targets are configured (tool won't be registered).
    """
    if not raw_targets:
        return None

    targets = tuple(
        NotifyTarget(
            channel=entry["channel"],
            recipient_id=entry["recipient_id"],
            label=entry.get("label", ""),
        )
        for entry in raw_targets
    )

    sender = ChannelNotificationSender(targets)
    config = NotifyToolConfig(
        allowed_targets=targets,
        rate_limit_per_session=10,
        max_body_length=4000,
    )
    return sender, config
