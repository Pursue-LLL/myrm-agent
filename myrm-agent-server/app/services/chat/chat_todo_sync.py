"""Session-tree bound todo state resolution and rewind synchronization service.

[INPUT]
- myrm_agent_harness.api::fold_branch_todo_state (POS: Branch state replayer)
- myrm_agent_harness.agent.meta_tools.progress.schemas::TodoStore (POS: Todo domain model)
- myrm_agent_harness.agent.meta_tools.progress.storage::read/write todos (POS: Workspace storage)
- app.services.chat.chat_service::ChatService (POS: Chat message history facade)

[OUTPUT]
- resolve_session_todo_store: Resolves authoritative todo store with branch-fold priority
- sync_workspace_todos_after_rewind: Realigns workspace progress file with remaining messages

[POS]
Provides service-layer business logic for active conversation branch todo folding
and physical workspace alignment after conversation rewind mutations.
"""

from __future__ import annotations

import logging
from pathlib import Path

from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    read_todos_sync_from_workspace,
    todos_path,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.api import fold_branch_todo_state
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config import settings
from app.platform_utils.workspace_session import to_workspace_session_id

logger = logging.getLogger(__name__)


async def _resolve_workspace_root_safely(session_id: str) -> str | None:
    """Safely resolve the physical workspace root directory for a session."""
    try:
        harness_dir = settings.get_settings().database.harness_dir
        if not harness_dir:
            return None
        workspace_svc = create_workspace_service(root_dir=Path(harness_dir))
        workspace_session_id = to_workspace_session_id(session_id)
        workspace = await workspace_svc.get_or_create(session_id=workspace_session_id)
        return str(workspace_svc.get_workspace_absolute_path(workspace))
    except Exception as exc:
        logger.debug("Failed to resolve workspace root for session %s: %s", session_id, exc)
        return None


async def resolve_session_todo_store(session_id: str) -> TodoStore | None:
    """Resolve authoritative TodoStore with active conversation branch priority.

    Strategy:
    1. Query all active messages on the current conversation branch and fold them.
       This isolates forked branches and automatically adapts to rewound message history.
    2. Fallback to physical workspace file if message folding yielded no todo state.
    """
    from app.services.chat.chat_service import ChatService

    try:
        messages = await ChatService.get_all_messages(session_id)
        if messages:
            branch_store = fold_branch_todo_state(messages)
            if branch_store is not None:
                return branch_store
    except Exception as exc:
        logger.debug("Failed to fold todo state from conversation branch %s: %s", session_id, exc)

    workspace_root = await _resolve_workspace_root_safely(session_id)
    if not workspace_root:
        return None

    try:
        return read_todos_sync_from_workspace(workspace_root)
    except Exception as exc:
        logger.debug("Failed to read fallback workspace todos for session %s: %s", session_id, exc)
        return None


async def sync_workspace_todos_after_rewind(chat_id: str) -> None:
    """Resynchronize workspace todos.json with folded state of remaining messages after rewind.

    Prevents split-brain state where physical workspace retains future tasks from deleted turns.
    """
    from app.services.chat.chat_service import ChatService

    try:
        workspace_root = await _resolve_workspace_root_safely(chat_id)
        if not workspace_root:
            return

        messages = await ChatService.get_all_messages(chat_id)
        remaining_store = fold_branch_todo_state(messages) if messages else None

        if remaining_store is not None and remaining_store.todos:
            write_todos_sync_to_workspace(workspace_root, remaining_store)
        elif not messages:
            # All messages in the conversation were rewound (cleared to initial state)
            path = todos_path(workspace_root)
            if path.is_file():
                path.unlink(missing_ok=True)
        else:
            # Remaining messages exist, but fold yielded no todo store.
            # Guard against aggressive deletion of pre-existing workspace files.
            logger.debug(
                "Skipping workspace todos unlink after rewind for chat %s: messages exist but no folded store",
                chat_id,
            )
    except Exception as exc:
        logger.warning("Failed to sync workspace todos after rewind for chat %s: %s", chat_id, exc)


__all__ = [
    "resolve_session_todo_store",
    "sync_workspace_todos_after_rewind",
]
