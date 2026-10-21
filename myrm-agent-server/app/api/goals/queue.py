"""Goal queue HTTP API endpoints.

[INPUT]
- app.services.agent.goals.goal_registry::GoalRegistry (POS: In-memory goal provider registry)
- myrm_agent_harness.agent.goals.manager::GoalManager (POS: Goal persistence manager fallback)

[OUTPUT]
- queue_router: APIRouter for queue management endpoints

[POS]
Provides HTTP endpoints for managing queued goals within a session.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.agent.goals.goal_registry import GoalRegistry

logger = logging.getLogger(__name__)

queue_router = APIRouter()


class QueueReorderRequest(BaseModel):
    ordered_goal_ids: list[str]


@queue_router.get("/{session_id}/queue")
async def get_goal_queue(session_id: str) -> dict[str, object]:
    """Get all queued goals for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    queued = await provider.get_queued_goals(session_id)
    return {"queue": [g.to_dict() for g in queued]}


@queue_router.delete("/{session_id}/queue/{goal_id}")
async def cancel_queued_goal(session_id: str, goal_id: str) -> dict[str, str]:
    """Cancel (remove) a specific goal from the queue."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    try:
        await provider.cancel_queued_goal(session_id, goal_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Queued goal not found") from None
    return {"status": "success", "goal_id": goal_id}


@queue_router.post("/{session_id}/queue/reorder")
async def reorder_goal_queue(session_id: str, request: QueueReorderRequest) -> dict[str, str]:
    """Reorder the goal queue by providing ordered goal IDs."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    await provider.reorder_queue(session_id, request.ordered_goal_ids)
    return {"status": "success"}


__all__ = ["QueueReorderRequest", "queue_router"]
