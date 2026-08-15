"""Session continuity orchestration — DB history to LangGraph checkpoint SSOT.

[INPUT]
- app.services.chat.chat_service::ChatService (POS: load web chat history)
- app.core.utils.chat_utils::convert_chat_history (POS: DB history → LangChain)
- app.platform_utils::get_checkpointer (POS: LangGraph checkpointer)
- app.services.agent.gateway::get_agent_gateway (POS: active session guard)
- app.services.agent.goals.goal_registry::GoalRegistry (POS: goal pause on rewind)

[OUTPUT]
- SessionBusyError: raised when chat session is actively streaming
- sync_chat_checkpoint_from_db: align checkpoint with persisted messages (propagates ContinuitySyncError)
- pause_active_goal_for_rewind: pause running goal after successful rewind mutation
- ContinuitySyncError: re-export harness checkpoint sync failure
- assert_session_available_for_continuity: guard against in-flight agent runs

[POS]
Server-layer adapter for truncate/undo/retry/rewind checkpoint consistency.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.runtime.context.session.session_continuity import (
    ContinuitySyncError,
    sync_checkpoint_messages,
)

__all__ = [
    "ContinuitySyncError",
    "SessionBusyError",
    "assert_session_available_for_continuity",
    "pause_active_goal_for_rewind",
    "sync_chat_checkpoint_from_db",
]

from app.core.utils.chat_utils import convert_chat_history
from app.services.agent.gateway import get_agent_gateway
from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


class SessionBusyError(Exception):
    """Raised when continuity mutation is rejected because the agent is working."""


def assert_session_available_for_continuity(chat_id: str) -> None:
    """Fail fast when the chat session has an in-flight agent execution."""
    gateway = get_agent_gateway()
    if gateway.is_session_active(chat_id):
        raise SessionBusyError(f"Session {chat_id} is busy")


async def sync_chat_checkpoint_from_db(chat_id: str) -> int:
    """Load persisted chat history and rewrite LangGraph checkpoint messages."""
    from app.platform_utils import get_checkpointer

    history = await ChatService.load_web_chat_history(chat_id, api_key=None)
    messages = await convert_chat_history(history) if history else []
    checkpointer = get_checkpointer()
    synced = await sync_checkpoint_messages(checkpointer, chat_id, messages)
    logger.info(
        "Synced checkpoint from DB for chat=%s (messages=%d, threads=%d)",
        chat_id,
        len(messages),
        synced,
    )
    return synced


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
