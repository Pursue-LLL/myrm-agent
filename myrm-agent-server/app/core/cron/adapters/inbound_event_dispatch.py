"""Dispatch cron event triggers for inbound channel messages.

Single entry point wired from AgentRouter after approval/reaction/slash
filtering so event-triggered CronJobs behave the same in every deployment mode.

[INPUT]
- app.core.cron.adapters.setup::get_cron_scheduler (POS: Cron scheduler singleton)

[OUTPUT]
- dispatch_cron_event_for_inbound_message: Match and spawn event-triggered jobs

[POS]
Server adapter — wires inbound IM text to harness CronScheduler.dispatch_event.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


async def dispatch_cron_event_for_inbound_message(
    message: str,
    channel: str,
    user_id: str,
) -> int:
    """Check event triggers against an inbound channel message.

    Returns the number of cron jobs spawned. Failures are logged and swallowed
    so channel routing is never blocked by cron side effects.
    """
    if not message.strip():
        return 0

    try:
        from app.core.cron.adapters.setup import get_cron_scheduler

        scheduler = get_cron_scheduler()
        return await scheduler.dispatch_event(message, channel, user_id)
    except Exception as exc:
        logger.warning(
            "Cron event dispatch failed for inbound message on channel %s: %s",
            channel,
            exc,
        )
        return 0
