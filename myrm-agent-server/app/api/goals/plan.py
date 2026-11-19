"""Goal plan HTTP API endpoint.

[INPUT]
- app.services.chat.chat_todo_sync::resolve_session_todo_store (POS: Authoritative branch todo resolver)

[OUTPUT]
- plan_router: APIRouter for the plan progress endpoint
- get_goal_plan: HTTP endpoint returning plan-compatible task progression

[POS]
Provides the HTTP endpoint for goal plan progress, delegating state resolution to
the chat_todo_sync domain service.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.services.chat.chat_todo_sync import resolve_session_todo_store

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


__all__ = [
    "get_goal_plan",
    "plan_router",
]
