"""Handlers for harness-level idle tasks injected by the server.

[INPUT]
- myrm_agent_harness.agent.background_worker.idle_tasks::register_idle_task_handler (POS: Default callbacks and tasks for the idle worker.)
- app.services.chat.compact_service::compact_chat (POS: Lossless context compaction service.)

[OUTPUT]
- context_compact_impl: Idle task handler for context compression during user inactivity.
- register_all_idle_handlers: Register all server-level idle task handlers with Harness.

[POS]
Server-side idle task handlers. Provides concrete business implementations
for harness-level idle background tasks (context compaction).
"""

import logging

from myrm_agent_harness.agent.background_worker.idle_tasks import register_idle_task_handler

logger = logging.getLogger(__name__)


async def context_compact_impl(chat_id: str, session_id: str) -> dict[str, object]:
    """Idle compression handler: compact chat context during user inactivity.

    Calls the existing compact_chat service to generate a structured summary
    of older messages. The summary is persisted and will reduce token costs
    on the next agent run.
    """
    from app.database.connection import get_session
    from app.services.chat.compact_service import compact_chat

    async with get_session() as db:
        result = await compact_chat(db, chat_id)

    return {
        "compacted": result.compacted,
        "tokens_saved": result.tokens_saved,
        "message_count": result.message_count,
        "reason": result.reason or "",
    }


def register_all_idle_handlers() -> None:
    """Register all server-level idle task handlers."""
    register_idle_task_handler("_context_compact_impl", context_compact_impl)
    logger.info("Registered server-level idle task handlers")
