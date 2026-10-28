"""Harness async wakeup bridge — hands a finished background subagent to the adaptive wakeup service.

[INPUT]
- app.services.agent.adaptive_wakeup::get_adaptive_wakeup_service (POS: routes a settlement, writes its notice row, queues the wake turn)
- app.services.agent.params.workspace_resolve::chat_id_from_session_id (POS: the chat a harness session key belongs to)
- myrm_agent_harness.agent.sub_agents.types::SubAgentResult (POS: the settled subagent)

[OUTPUT]
- ServerWakeupHandler.on_async_wakeup: settle a finished background subagent into its chat

[POS]
Business orchestration hook for Harness `ASYNC_WAKEUP`; runs per isolated server instance without Control Plane scheduling.
The harness reports the session key of the run that started the subagent; this hook turns it into the chat id the
service works with. Building and streaming the wake turn belongs to `adaptive_wakeup/wake_turn_stream.py`.
"""

from __future__ import annotations

import asyncio
import logging

from myrm_agent_harness.agent.coordination.adaptive_wakeup import WakeupEvent, WakeupSourceType
from myrm_agent_harness.agent.sub_agents.types import SubAgentResult

from app.services.agent.adaptive_wakeup import get_adaptive_wakeup_service
from app.services.agent.params.workspace_resolve import chat_id_from_session_id

logger = logging.getLogger(__name__)

_tasks: set[asyncio.Task[None]] = set()


class ServerWakeupHandler:
    """Handles async wakeup events from the Harness framework in the background."""

    async def on_async_wakeup(self, result: SubAgentResult, agent_id: str, session_id: str | None) -> None:
        """Called by Harness when a background subagent (wait=False) completes.

        The settlement is routed in a detached task so the harness cleanup hook is not blocked. The wake turn belongs
        to the chat's own agent, so ``agent_id`` is not needed.
        """
        if not session_id:
            logger.warning("Wakeup handler received event without session_id. Ignoring.")
            return

        chat_id = chat_id_from_session_id(session_id)
        logger.info("ServerWakeupHandler received wakeup for session %s, task %s", chat_id, result.task_id)

        task = asyncio.create_task(self._process_wakeup(result, chat_id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)

    @staticmethod
    async def _process_wakeup(result: SubAgentResult, chat_id: str) -> None:
        """Hand the settled subagent to the adaptive wakeup service in a detached background task."""
        status_str = "completed successfully" if result.success else "failed"
        event = WakeupEvent(
            source_type=WakeupSourceType.SUBAGENT,
            source_id=result.task_id,
            session_id=chat_id,
            success=result.success,
            summary=f"Subagent '{result.agent_type}' {status_str}",
            duration_seconds=result.duration_seconds,
            error=result.error,
        )
        try:
            await get_adaptive_wakeup_service().handle_settlement(event)
        except Exception as e:
            logger.error("Failed to process async wakeup for session %s: %s", chat_id, e, exc_info=True)
