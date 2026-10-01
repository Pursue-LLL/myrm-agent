"""Goal plan and DAG HTTP API endpoints.

[INPUT]
- app.services.chat.chat_todo_sync::resolve_session_todo_store (POS: Authoritative branch todo resolver)
- app.services.chat.chat_todo_sync::sync_workspace_todos_after_rewind (POS: Rewind workspace synchronizer)

[OUTPUT]
- plan_router: APIRouter for plan and DAG progress endpoints
- get_goal_plan: HTTP endpoint returning plan-compatible task progression
- get_goal_dag: HTTP endpoint returning DAG-compatible node list

[POS]
Provides HTTP endpoints for goal plan progress, delegating state resolution to
the chat_todo_sync domain service.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.services.chat.chat_todo_sync import (
    resolve_session_todo_store,
    sync_workspace_todos_after_rewind,
)

logger = logging.getLogger(__name__)

plan_router = APIRouter()


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
