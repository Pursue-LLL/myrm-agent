"""Goal plan and DAG HTTP API endpoints with branch state replayer.

[INPUT]
- myrm_agent_harness.runtime.context.tree_state::fold_branch_todo_state (POS: Branch state replayer)
- myrm_agent_harness.agent.meta_tools.progress.schemas::TodoStore (POS: Todo store domain model)
- myrm_agent_harness.agent.meta_tools.progress.storage::read/write todos (POS: Workspace storage)
- app.services.chat.chat_service::ChatService (POS: Chat message history facade)

[OUTPUT]
- plan_router: APIRouter for plan and DAG progress endpoints
- resolve_session_todo_store: Resolves authoritative todo store with branch-fold priority
- sync_workspace_todos_after_rewind: Realigns workspace progress file with remaining messages

[POS]
Provides branch-isolated, rewind-aware task plan endpoints.
Replaces single global file reads with active conversation branch fold replaying.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.agent.meta_tools.progress.schemas import TodoStore
from myrm_agent_harness.agent.meta_tools.progress.storage import (
    read_todos_sync_from_workspace,
    todos_path,
    write_todos_sync_to_workspace,
)
from myrm_agent_harness.runtime.context.tree_state import fold_branch_todo_state
from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config import settings
from app.platform_utils.workspace_session import to_workspace_session_id
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)

plan_router = APIRouter()


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
    try:
        workspace_root = await _resolve_workspace_root_safely(chat_id)
        if not workspace_root:
            return

        messages = await ChatService.get_all_messages(chat_id)
        remaining_store = fold_branch_todo_state(messages) if messages else None

        if remaining_store is not None and remaining_store.todos:
            write_todos_sync_to_workspace(workspace_root, remaining_store)
        else:
            path = todos_path(workspace_root)
            if path.is_file():
                path.unlink(missing_ok=True)
    except Exception as exc:
        logger.warning("Failed to sync workspace todos after rewind for chat %s: %s", chat_id, exc)


@plan_router.get("/{session_id}/plan")
async def get_goal_plan(session_id: str) -> dict[str, object]:
    """Get the current todo progress for a session's goal (plan-compat shape)."""
    try:
        store = await resolve_session_todo_store(session_id)
        if not store or not store.todos:
            return {"plan": None}

        return {"plan": store.to_plan_compat()}
    except Exception as exc:
        logger.error("Failed to get goal progress: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to get goal progress") from exc


@plan_router.get("/{session_id}/dag")
async def get_goal_dag(session_id: str) -> dict[str, object]:
    """Flat todo nodes for legacy DAG consumers (linear todos, no dependency edges)."""
    try:
        store = await resolve_session_todo_store(session_id)
        if not store or not store.todos:
            return {"nodes": [], "edges": []}

        nodes = [
            {
                "id": item.id,
                "data": {
                    "label": item.content,
                    "status": item.status.value,
                    "expected_output": "",
                    "risk_level": "low",
                },
            }
            for item in store.todos
        ]
        return {"nodes": nodes, "edges": []}
    except Exception as exc:
        logger.error("Failed to get goal DAG: %s", exc)
        raise HTTPException(status_code=500, detail="Failed to get goal DAG") from exc


__all__ = [
    "get_goal_dag",
    "get_goal_plan",
    "plan_router",
    "resolve_session_todo_store",
    "sync_workspace_todos_after_rewind",
]
