"""Global registry for async wakeup events (Idle Wakeup).

Provides a decoupling mechanism for the Harness framework to notify
the Server layer when an asynchronous background subagent completes.

[INPUT]
- agent.sub_agents.types::SubAgentResult (POS: structured result of a subagent run)

[OUTPUT]
- AsyncWakeupHandler: Protocol for handling asynchronous wakeup events from background subagents.
- set_global_wakeup_handler: Register a global handler for async wakeup events.
- get_global_wakeup_handler: Retrieve the registered global wakeup handler.
- report_results_read: Tell the handler the parent agent read settled results (a subagent's or a background job's) itself.
- wake_session_id: The session key a wake turn is queued and stood down under, derived from the run context.

[POS]
Global registry for async wakeup events (Idle Wakeup).
A wakeup exists to deliver a result the parent has not seen; when the parent reads it first, the handler is told so
the wake turn it queued can stand down. The wakeup and the read report both name the session through
``wake_session_id``, so they agree on the key.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, Mapping
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
        """Called when the parent agent read the settled results of these subagents or background jobs itself.

        Args:
            task_ids: The subagent task ids or background job ids whose results the parent's own tool call returned.
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


def wake_session_id(context: Mapping[str, object] | None) -> str | None:
    """The session key a wake turn is queued and stood down under: the context's ``session_id`` as ``str``.

    A host may carry its session id as ``int`` or ``UUID`` while the handler keys by the string form, so the wakeup
    that queues the wake turn and the read report that stands it down must both derive the key here.
    """
    raw = None if context is None else context.get("session_id")
    return None if raw is None else str(raw)


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
