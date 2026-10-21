"""Session continuity orchestration — persisted history owns the conversation.

[INPUT]
- app.platform_utils::get_checkpointer (POS: LangGraph checkpointer)
- app.services.agent.gateway::get_agent_gateway (POS: active session guard)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: goal pause on rewind)

[OUTPUT]
- SessionBusyError: raised when chat session is actively streaming
- invalidate_chat_checkpoint: drop the chat's checkpoint threads so the next run
  rebuilds them from persisted history (propagates CheckpointClearError)
- pause_active_goal_for_rewind: pause running goal after successful rewind mutation
- CheckpointClearError: re-export harness checkpoint-clear failure
- assert_session_available_for_continuity: guard against in-flight agent runs

[POS]
Server-layer adapter for truncate/undo/retry/rewind checkpoint consistency.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.runtime.context.session.session_continuity import (
    CheckpointClearError,
    clear_checkpoint_threads,
)

__all__ = [
    "CheckpointClearError",
    "SessionBusyError",
    "assert_session_available_for_continuity",
    "pause_active_goal_for_rewind",
    "invalidate_chat_checkpoint",
]

from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.goal_registry import GoalRegistry

logger = logging.getLogger(__name__)


class SessionBusyError(Exception):
    """Raised when continuity mutation is rejected because the agent is working."""


def assert_session_available_for_continuity(chat_id: str) -> None:
    """Fail fast when the chat session has an in-flight agent execution."""
    gateway = get_agent_gateway()
    if gateway.is_session_active(chat_id):
        raise SessionBusyError(f"Session {chat_id} is busy")


async def invalidate_chat_checkpoint(chat_id: str) -> int:
    """Drop the chat's checkpoint threads; the next run rebuilds from persisted history."""
    from app.platform_utils import get_checkpointer

    cleared = await clear_checkpoint_threads(get_checkpointer(), chat_id)
    logger.info("Cleared checkpoint threads for chat=%s (threads=%d)", chat_id, cleared)
    return cleared


async def pause_active_goal_for_rewind(chat_id: str) -> bool:
    """Pause an active goal after a successful rewind mutation."""
    provider = GoalRegistry.get_provider(chat_id)
    if provider is None:
        return False

    goal = await provider.get_active_goal(chat_id)
    if goal is None or goal.status != GoalStatus.ACTIVE:
        return False

    await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
    if hasattr(provider, "update_metadata"):
        await provider.update_metadata(
            goal.goal_id,
            {"pause_reason": "Conversation rewind requested"},
        )
    logger.info("Paused active goal %s after rewind (chat=%s)", goal.goal_id, chat_id)
    return True
