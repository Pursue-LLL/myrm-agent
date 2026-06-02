"""ChannelNotificationSender — Server-layer implementation of NotificationSender.

Routes agent-initiated notifications through the ChannelGateway/MessageBus
infrastructure, reusing existing retry, DLQ, and rate-limiting mechanisms.

[INPUT]
- myrm_agent_harness.toolkits.notification (POS: notification toolkit protocol/types)
- app.channels.core.gateway (POS: channel gateway singleton)
- app.channels.types::OutboundMessage (POS: outbound message model)

[OUTPUT]
- ChannelNotificationSender: Concrete NotificationSender implementation.
- create_notification_sender: Factory from ResolvedAgentProfile notify_targets.

[POS]
Server-layer notification delivery using ChannelGateway. Pure addition to the
channel infrastructure — no schema changes, no side effects on existing flows.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.notification import (
    NotifyResult,
    NotifyTarget,
    NotifyToolConfig,
)

logger = logging.getLogger(__name__)


class ChannelNotificationSender:
    """Sends notifications via ChannelGateway.publish().

    This implementation satisfies the NotificationSender protocol from
    myrm-agent-harness. It bridges the framework tool with the server's
    channel infrastructure.
    """

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
        except Exception as e:
            logger.warning(
                "Notification delivery failed: channel=%s, recipient=%s, error=%s",
                target.channel,
                target.recipient_id,
                e,
            )
            return NotifyResult(
                success=False,
                channel=target.channel,
                error=str(e),
            )

    async def list_available_targets(self) -> list[NotifyTarget]:
        """Return configured targets."""
        return list(self._targets)


def create_notification_sender(
    raw_targets: tuple[dict[str, str], ...],
) -> tuple[ChannelNotificationSender, NotifyToolConfig] | None:
    """Create sender + config from agent profile's notify_targets.

    Returns None if no targets are configured (tool won't be registered).
    """
    if not raw_targets:
        return None

    targets = tuple(
        NotifyTarget(
            channel=t["channel"],
            recipient_id=t["recipient_id"],
            label=t.get("label", ""),
        )
        for t in raw_targets
    )

    sender = ChannelNotificationSender(targets)
    config = NotifyToolConfig(
        allowed_targets=targets,
        rate_limit_per_session=10,
        max_body_length=4000,
    )
    return sender, config
