"""Session continuity orchestration — persisted history owns the conversation.

[INPUT]
- app.platform_utils::get_checkpointer (POS: LangGraph checkpointer)
- app.services.agent.adaptive_wakeup.chat_busy::is_chat_busy (POS: whether a turn outside the agent gateway, an IM turn, holds the chat)
- app.services.agent.gateway::AgentBusyError, AgentDrainingError (POS: Agent execution gateway; its session registry is the per-chat lock between turns)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: the chat's goal provider, for the goal pause on rewind)
- app.services.agent.streaming_support.stream_collector::release_parked_hitl (POS: Agent API persistence helper. Converts transient SSE events into durable Message.extra_data metadata, and holds the registry of each chat's parked run)
- app.services.agent.turn_lease::hold_chat (POS: a chat's gateway session held for a rewrite of its history, with no turn and no cancel token)

[OUTPUT]
- SessionBusyError: raised when a turn holds the chat, an IM turn is running in it, or the gateway is draining
- hold_session_for_continuity: async context manager that holds the chat while a history mutation runs, so no entry
  that reserves the chat first starts in between (raises SessionBusyError)
- invalidate_chat_checkpoint: drop the chat's checkpoint threads, and retire the card a parked run holds in them,
  so the next run rebuilds the threads from persisted history (propagates CheckpointClearError)
- pause_active_goal_for_rewind: pause running goal after successful rewind mutation
- CheckpointClearError: re-export harness checkpoint-clear failure

[POS]
Server-layer adapter for truncate/undo/retry/rewind checkpoint consistency.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.runtime.context.session.session_continuity import (
    CheckpointClearError,
    clear_checkpoint_threads,
)

__all__ = [
    "CheckpointClearError",
    "SessionBusyError",
    "hold_session_for_continuity",
    "pause_active_goal_for_rewind",
    "invalidate_chat_checkpoint",
]

from app.services.agent.adaptive_wakeup.chat_busy import is_chat_busy
from app.services.agent.gateway import AgentBusyError, AgentDrainingError
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.agent.streaming_support.stream_collector import release_parked_hitl
from app.services.agent.turn_lease import hold_chat

logger = logging.getLogger(__name__)


class SessionBusyError(Exception):
    """A continuity mutation is refused: a turn holds the chat, an IM turn is running in it, or the gateway is draining."""


@asynccontextmanager
async def hold_session_for_continuity(chat_id: str) -> AsyncIterator[None]:
    """Hold the chat while its persisted history is rewritten in several steps.

    A turn that reserves the chat before it persists anything (a message, a goal continuation, an approval resumed
    after its timeout, a replayed turn, a wake turn) is refused while the hold lasts, so it cannot start between the
    steps and have its fresh messages deleted by the last one. An IM turn is not reserved at the gateway: one that is
    running is found through the busy probe and refused here, one that starts during the hold is not kept out. The
    voice and OpenAI-compatible entries do not reserve the chat either.

    Raises:
        SessionBusyError: a turn holds the chat, an IM turn is running in it, or the gateway is draining.
    """
    # Nothing may suspend between this question and the reservation below: the answer holds only until another task runs.
    if is_chat_busy(chat_id):
        raise SessionBusyError(f"Session {chat_id} is busy")
    async with AsyncExitStack() as held:
        # Only the refusal to enter is a busy chat; whatever the caller's own body raises passes through untouched.
        try:
            await held.enter_async_context(hold_chat(chat_id))
        except (AgentBusyError, AgentDrainingError) as exc:
            raise SessionBusyError(f"Session {chat_id} is busy") from exc
        yield


async def invalidate_chat_checkpoint(chat_id: str) -> int:
    """Drop the chat's checkpoint threads and retire the card a parked run holds in them; the next run rebuilds from persisted history.

    The rewritten history no longer contains the turn the card paused, so its timer must not resume it, whether or not the
    threads could be cleared.
    """
    from app.platform_utils import get_checkpointer

    release_parked_hitl(chat_id)
    cleared = await clear_checkpoint_threads(get_checkpointer(), chat_id)
    logger.info("Cleared checkpoint threads for chat=%s (threads=%d)", chat_id, cleared)
    return cleared


async def pause_active_goal_for_rewind(chat_id: str) -> bool:
    """Pause an active goal after a successful rewind mutation.

    A rewind holds the chat (`hold_session_for_continuity`): no turn that reserves the chat is running, so no provider
    of one is registered and the goal is read from storage.
    """
    provider = GoalRegistry.resolve_provider(chat_id)

    goal = await provider.get_active_goal(chat_id)
    if goal is None or goal.status != GoalStatus.ACTIVE:
        return False

    await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
    await provider.update_metadata(
        goal.goal_id,
        {"pause_reason": "Conversation rewind requested"},
    )
    logger.info("Paused active goal %s after rewind (chat=%s)", goal.goal_id, chat_id)
    return True
