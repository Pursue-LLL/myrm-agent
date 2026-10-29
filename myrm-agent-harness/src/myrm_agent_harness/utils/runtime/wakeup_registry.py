"""Global registry for async wakeup events (Idle Wakeup).

Provides a decoupling mechanism for the Harness framework to notify
the Server layer when an asynchronous background subagent completes.

[INPUT]
- agent.sub_agents.types::SubAgentResult (POS: Provides ArtifactInfo, infer_language, infer_artifact_type.)

[OUTPUT]
- AsyncWakeupHandler: Protocol for handling asynchronous wakeup events from bac...
- set_global_wakeup_handler: Register a global handler for async wakeup events.
- get_global_wakeup_handler: Retrieve the registered global wakeup handler.
- report_results_read: Tell the handler the parent agent read settled subagent results itself.

[POS]
Global registry for async wakeup events (Idle Wakeup).
A wakeup exists to deliver a result the parent has not seen; when the parent reads it first, the handler is told so
the wake turn it queued can stand down.
"""

from __future__ import annotations

import logging
from collections.abc import Collection
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from myrm_agent_harness.agent.sub_agents.types import SubAgentResult


class AsyncWakeupHandler(Protocol):
    """Protocol for handling asynchronous wakeup events from background subagents."""

    async def on_async_wakeup(self, result: SubAgentResult, agent_id: str, session_id: str | None) -> None:
        """Called when an async background subagent completes.

        Args:
            result: The result of the subagent execution.
            agent_id: The ID of the parent agent that spawned the subagent.
            session_id: The session/chat ID to resume (if any).
        """
        ...

    def on_results_read(self, task_ids: Collection[str], session_id: str | None) -> None:
        """Called when the parent agent read the settled results of these subagents itself.

        Args:
            task_ids: The subagents whose results the parent's own tool call returned.
            session_id: The session/chat ID of the parent agent (if any).
        """
        ...


logger = logging.getLogger(__name__)

_global_wakeup_handler: AsyncWakeupHandler | None = None


def set_global_wakeup_handler(handler: AsyncWakeupHandler | None) -> None:
    """Register a global handler for async wakeup events."""
    global _global_wakeup_handler
    _global_wakeup_handler = handler


def get_global_wakeup_handler() -> AsyncWakeupHandler | None:
    """Retrieve the registered global wakeup handler."""
    return _global_wakeup_handler


def report_results_read(task_ids: Collection[str], session_id: str | None) -> None:
    """Tell the registered handler the parent agent read these settled results itself.

    The reading tool call must not fail because the handler did, so a handler error is logged and dropped.
    """
    handler = _global_wakeup_handler
    if handler is None or not task_ids:
        return
    try:
        handler.on_results_read(task_ids, session_id)
    except Exception:
        logger.warning("Wakeup handler failed to record read results (session_id=%s)", session_id, exc_info=True)
