"""Dispatch cron event triggers for inbound channel messages.

Single entry point wired from AgentRouter after approval/reaction/slash
filtering so event-triggered CronJobs behave the same in every deployment mode.

[INPUT]
- app.core.cron.adapters.setup::get_cron_scheduler (POS: Cron scheduler singleton)
- app.services.risk.ingress::screen_user_text (POS: risk gate for text a user typed)
- myrm_agent_harness.api.security::untrusted_ingress_scope (POS: tool-privilege fence for work a non-owner starts)

[OUTPUT]
- dispatch_cron_event_for_inbound_message: Match and spawn event-triggered jobs; a message a risk rule holds starts none; jobs a non-owner's message starts run fenced

[POS]
Server adapter — wires inbound IM text to harness CronScheduler.dispatch_event. A job's context carries the matched
message verbatim, so the message passes the risk gate before any job is spawned.
"""

from __future__ import annotations

import logging
from contextlib import nullcontext

from myrm_agent_harness.api.security import untrusted_ingress_scope

from app.services.risk.ingress import screen_user_text

logger = logging.getLogger(__name__)


async def dispatch_cron_event_for_inbound_message(
    message: str,
    channel: str,
    user_id: str,
    *,
    untrusted: bool,
) -> int:
    """Check event triggers against an inbound channel message.

    ``untrusted`` marks a sender other than the owner. The jobs its message starts inherit the untrusted-ingress
    fence from the tasks the scheduler spawns, so they get the tool restrictions a chat turn from that sender gets.

    A message a risk rule holds spawns no job: a job's context carries the text verbatim, and the chat turn of the same
    message is held. The sender is not told here; the turn path of that message replies.

    Returns the number of cron jobs spawned. Failures are logged and swallowed
    so channel routing is never blocked by cron side effects; a failed screening spawns nothing.
    """
    if not message.strip():
        return 0

    try:
        held = await screen_user_text(message, session_id=user_id or None)
        if held is not None:
            logger.info(
                "Event dispatch skipped a message held by the risk gate on channel %s: rules=%s",
                channel,
                [m.display_name for m in held.matches],
            )
            return 0

        from app.core.cron.adapters.setup import get_cron_scheduler

        scheduler = get_cron_scheduler()
        fence = untrusted_ingress_scope() if untrusted else nullcontext()
        with fence:
            return await scheduler.dispatch_event(message, channel, user_id)
    except Exception as exc:
        logger.warning(
            "Cron event dispatch failed for inbound message on channel %s: %s",
            channel,
            exc,
        )
        return 0
