"""Handlers for harness-level idle tasks injected by the server.

[INPUT]
- myrm_agent_harness.agent.background_worker.idle_tasks::register_idle_task_handler (POS: Default callbacks and tasks for the idle worker.)
- app.api.dependencies::get_llm_for_user (POS: FastAPI dependency injection.)
- app.config.settings::settings (POS: Application settings.)
- app.database.connection::get_session (POS: Database session factory.)
- app.services.chat.compact_service::compact_chat (POS: Lossless context compaction service.)

[OUTPUT]
- wiki_maintenance_handler: Idle task handler for wiki linting and maintenance.
- context_compact_impl: Idle task handler for context compression during user inactivity.
- register_all_idle_handlers: Register all server-level idle task handlers with Harness.

[POS]
Server-side idle task handlers. Provides concrete business implementations
for harness-level idle background tasks (wiki maintenance, context compaction).
"""

import logging
from pathlib import Path

from myrm_agent_harness.agent.background_worker.idle_tasks import register_idle_task_handler

from app.api.dependencies import get_llm_for_user
from app.config.settings import settings

logger = logging.getLogger(__name__)


def _model_dump_as_objects(result: object) -> dict[str, object]:
    md = getattr(result, "model_dump", None)
    if callable(md):
        dumped = md()
        if isinstance(dumped, dict):
            return {str(k): v for k, v in dumped.items()}
        return {}
    d = getattr(result, "__dict__", None)
    if isinstance(d, dict):
        return {str(k): v for k, v in d.items()}
    return {}


async def wiki_maintenance_handler(task: object, session_id: str) -> dict[str, object]:
    from myrm_agent_harness.runtime.events.bus import get_event_bus
    from myrm_agent_harness.runtime.events.idle_events import IdleTaskProgressEvent
    from myrm_agent_harness.toolkits.wiki import WikiConfig, WikiLinter, WikiStructure

    event_bus = get_event_bus()

    user_id = str(getattr(task, "user_id", "") or "")
    task_type = str(getattr(task, "task_type", "") or "")

    event_bus.publish(
        IdleTaskProgressEvent(
            session_id=session_id,
            user_id=user_id,
            status="working",
            task_name=task_type,
            message="🌌 闲时梦境开启：正在对知识库进行自愈与梳理...",
            progress_pct=30,
        )
    )

    try:
        llm = await get_llm_for_user()

        base = Path(settings.database.state_dir).expanduser().resolve()
        user_wiki_dir = base / "users" / user_id / "wiki"
        structure = WikiStructure(user_wiki_dir)
        config = WikiConfig()
        linter = WikiLinter(llm, structure, config)

        result = await linter.lint_and_maintain()

        return _model_dump_as_objects(result)
    except Exception as e:
        logger.error(f"Wiki maintenance idle task failed: {e}", exc_info=True)
        raise


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
    register_idle_task_handler("wiki_maintenance", wiki_maintenance_handler)
    register_idle_task_handler("_context_compact_impl", context_compact_impl)
    logger.info("Registered server-level idle task handlers")
