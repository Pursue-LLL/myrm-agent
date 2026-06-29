"""ChannelGateway-backed outbound notification sender.

[INPUT]
- app.channels.core.gateway::ChannelGateway (POS: multi-platform channel gateway)
- app.channels.types::OutboundMessage (POS: outbound message model)
- .types::NotifyResult, NotifyTarget, NotifyToolConfig (POS: outbound notification data types)

[OUTPUT]
- ChannelNotificationSender: NotificationSender implementation via ChannelGateway.
- create_notification_sender: Factory from agent notify_targets.

[POS]
Channel delivery for agent-initiated outbound notifications.
"""

from __future__ import annotations

import logging

from .types import NotifyResult, NotifyTarget, NotifyToolConfig

logger = logging.getLogger(__name__)


class ChannelNotificationSender:
    """Sends notifications via ChannelGateway.publish()."""

    __slots__ = ("_targets",)

    def __init__(self, targets: tuple[NotifyTarget, ...]) -> None:
        self._targets = targets

    async def send(
        self,
        target: NotifyTarget,
        body: str,
    ) -> NotifyResult:
        """Deliver notification via ChannelGateway (always NORMAL priority)."""
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
            )
            await channel_gateway.publish(msg)

            logger.info(
                "Notification sent: channel=%s, recipient=%s, len=%d",
                target.channel,
                target.recipient_id,
                len(body),
            )
            return NotifyResult(
                success=True,
                channel=target.channel,
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
