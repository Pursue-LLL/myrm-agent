"""Session-tree bound todo state resolution and rewind synchronization service.

[INPUT]
- myrm_agent_harness.api::fold_branch_todo_state (POS: Branch state replayer)
- myrm_agent_harness.agent.meta_tools.progress.schemas::TodoStore (POS: Todo domain model)
- myrm_agent_harness.agent.meta_tools.progress.storage::read/write/delete todos (POS: Workspace storage, one list per chat)
- app.services.chat.chat_service::ChatService (POS: Chat message history facade)
- app.services.chat.effective_workspace::find_chat_workspace_root (POS: the workspace a chat's runs work in)

[OUTPUT]
- resolve_session_todo_store: Resolves authoritative todo store with branch-fold priority
- sync_workspace_todos_for_active_branch: Realigns workspace progress file with current active branch messages
- sync_workspace_todos_after_rewind: Backward-compatible alias for sync_workspace_todos_for_active_branch

[POS]
Provides service-layer business logic for active conversation branch todo folding
and physical workspace alignment after conversation tree mutations (rewind, retry, undo, sibling switch).
A chat's list lives in the workspace its runs work in (a project's directory is shared by all its chats),
under the chat's own directory, so the sync never reads or rewrites another chat's list.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    delete_todos_sync_from_workspace,
    read_todos_sync_from_workspace,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.api import fold_branch_todo_state

from app.platform_utils.workspace_session import to_rest_chat_id
from app.services.chat.effective_workspace import find_chat_workspace_root

logger = logging.getLogger(__name__)


async def _resolve_workspace_root_safely(chat_id: str) -> str | None:
    """Workspace root the runs of a chat work in: its project's directory, its own workspace, or its sandbox."""
    try:
        root = await find_chat_workspace_root(chat_id)
    except Exception as exc:
        logger.debug("Failed to resolve workspace root for chat %s: %s", chat_id, exc)
        return None
    return str(root) if root is not None else None


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

    chat_id = to_rest_chat_id(session_id)
    workspace_root = await _resolve_workspace_root_safely(chat_id) if chat_id else None
    if not chat_id or not workspace_root:
        return None

    try:
        return read_todos_sync_from_workspace(workspace_root, chat_id)
    except Exception as exc:
        logger.debug("Failed to read fallback workspace todos for session %s: %s", session_id, exc)
        return None


async def sync_workspace_todos_for_active_branch(chat_id: str) -> None:
    """Resynchronize the chat's workspace todos.json with folded state of current active branch messages.

    Prevents split-brain state where physical workspace retains future or abandoned
    tasks after rewind, retry, undo, or sibling branch switching.
    """
    from app.services.chat.chat_service import ChatService

    try:
        rest_chat_id = to_rest_chat_id(chat_id)
        workspace_root = await _resolve_workspace_root_safely(rest_chat_id) if rest_chat_id else None
        if not rest_chat_id or not workspace_root:
            return

        messages = await ChatService.get_all_messages(chat_id)
        remaining_store = fold_branch_todo_state(messages) if messages else None

        if remaining_store is not None and remaining_store.todos:
            write_todos_sync_to_workspace(workspace_root, remaining_store, rest_chat_id)
        elif not messages:
            # All messages in the conversation were rewound/cleared to initial state
            delete_todos_sync_from_workspace(workspace_root, rest_chat_id)
        else:
            # Remaining messages exist, but fold yielded no todo store.
            # Guard against aggressive deletion of pre-existing workspace files.
            logger.debug(
                "Skipping workspace todos unlink after mutation for chat %s: messages exist but no folded store",
                chat_id,
            )
    except Exception as exc:
        logger.warning("Failed to sync workspace todos for active branch on chat %s: %s", chat_id, exc)


sync_workspace_todos_after_rewind = sync_workspace_todos_for_active_branch


__all__ = [
    "resolve_session_todo_store",
    "sync_workspace_todos_after_rewind",
    "sync_workspace_todos_for_active_branch",
]
