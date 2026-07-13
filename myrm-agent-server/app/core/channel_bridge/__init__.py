"""Application-level channel gateway singleton.

Wraps the framework-level ChannelGateway from myrm_agent_harness.
Business-specific providers (ChatChannel, FeishuChannel) are registered
in the FastAPI lifespan.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.reliability.inbound_journal import (
    SqliteInboundJournal,
)
from app.channels.reliability.delivery_notify_ledger import SqliteDeliveryNotifyLedger
from app.config.settings import settings

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)

dlq_dir = Path(settings.database.state_dir) / "dlq"
dlq_dir.mkdir(parents=True, exist_ok=True)

_journal_db_path = Path(settings.database.state_dir) / "inbound_journal.db"
_inbound_journal = SqliteInboundJournal(db_path=_journal_db_path)
_notify_ledger_db_path = Path(settings.database.state_dir) / "delivery_notify_ledger.db"
_delivery_notify_ledger = SqliteDeliveryNotifyLedger(_notify_ledger_db_path)


def _extract_suppress_im_from_delivery(delivery: object) -> bool:
    from app.services.agent.outbound_notify.constants import (
        METADATA_KEY_NOTIFY_SOURCE,
        NOTIFY_SOURCE_AGENT,
    )

    content = getattr(delivery, "content", None)
    if not isinstance(content, dict):
        return False
    metadata = content.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return metadata.get(METADATA_KEY_NOTIFY_SOURCE) == NOTIFY_SOURCE_AGENT


async def handle_dead_letter(delivery: object, error_reason: str) -> None:
    """Handle dead letter callback from Harness DeliveryQueue."""
    import asyncio

    from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
    from app.services.infra.system_notification import SystemNotificationService

    try:
        channel = str(getattr(delivery, "channel", "") or "")
        delivery_id = str(getattr(delivery, "id", "") or "")

        # 1. Publish SSE event for frontend toast notification (real-time)
        event = AppEvent(
            event_type=AppEventType.MESSAGE_DEAD_LETTERED,
            data={
                "channel": channel,
                "error_reason": error_reason,
                "delivery_id": delivery_id,
                "suppress_im_notification": _extract_suppress_im_from_delivery(delivery),
            },
        )
        get_event_bus().publish(event)
        logger.warning("DLQ: Message permanently failed on channel %s: %s", channel, error_reason)

        # 2. Persist to database for offline retrieval
        async def _persist_notification() -> None:
            try:
                await SystemNotificationService.create_notification(
                    title="消息发送失败",
                    message=f"发送至 {channel} 的消息最终失败，已放弃重试。原因：{error_reason}",
                    type="error",
                    source="channel_gateway",
                    meta_data={"delivery_id": delivery_id},
                )
            except Exception as e:
                logger.error("Failed to persist DLQ notification: %s", e)

        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_persist_notification())
        except RuntimeError:
            logger.error("No running event loop to schedule DLQ notification persistence")

    except Exception as e:
        logger.error("Error handling dead letter callback: %s", e)


channel_gateway = ChannelGateway(
    dlq_dir=dlq_dir,
    on_permanent_failure=handle_dead_letter,
    inbound_journal=_inbound_journal,
    notification_ledger=_delivery_notify_ledger,
)


def get_channel_gateway() -> ChannelGateway:
    return channel_gateway


def _on_dlq_threshold_exceeded(emitter_name: str, data: object) -> None:
    """Handle DLQ threshold exceeded event."""
    if isinstance(data, dict):
        count = data.get("count", 0)
        channel = data.get("channel", "unknown")
        logger.error(
            f"ALERT: Dead Letter Queue size exceeded threshold! "
            f"Channel '{channel}' has {count} failed messages. "
            f"Please check channel credentials or network connectivity."
        )
        # In a real system, you might integrate with an email/slack alert service here


channel_gateway.bus.events.on("DLQ_THRESHOLD_EXCEEDED", _on_dlq_threshold_exceeded)


def check_channel_connected(ch: BaseChannel) -> bool:
    """Check if a channel has an active authenticated connection.

    Providers with ``get_status_info`` (e.g. WeChat) use a stricter check
    that validates credentials and poll-task liveness.  All other providers
    use the unified ``is_connected`` flag managed by ``_set_connected``.
    """
    status_fn = getattr(ch, "get_status_info", None)
    if callable(status_fn):
        info = status_fn()
        if isinstance(info, dict):
            return bool(info.get("connected", False))
        return False
    return bool(ch.is_connected)


def init_channel_routes(app: FastAPI) -> None:
    """Initialize dynamic channel routes after gateway is ready.

    Discovers channels from gateway and registers their custom HTTP routes
    (webhooks, login pages, status endpoints). Should be called after
    channel providers are registered with the gateway.

    Also sets up route health monitoring endpoint.

    Args:
        app: FastAPI application instance
    """
    from app.channels.implementations.fastapi import (
        ChannelRouteRegistry,
    )

    registry = ChannelRouteRegistry(channel_gateway, auth_dependency=None)
    registry.register_all(app)

    from app.core.channel_bridge.route_registry import set_route_registry

    set_route_registry(registry)
