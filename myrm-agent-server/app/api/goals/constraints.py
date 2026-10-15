"""Goal constraints and objective HTTP API endpoints.

[INPUT]
- app.services.agent.goals.goal_registry::GoalRegistry (POS: In-memory goal provider registry)
- myrm_agent_harness.agent.goals.manager::GoalManager (POS: Goal persistence manager fallback)
- myrm_agent_harness.agent.goals.steering_prompts::build_objective_updated_steering_message (POS: Steering message generator)
- app.services.agent.steering::SteeringRegistry (POS: Active agent steering registry)
- app.services.risk.ingress::screen_user_text (POS: Risk screening of text a user types before an agent reads it)

[OUTPUT]
- constraints_router: APIRouter for constraints and objective endpoints

[POS]
Provides HTTP endpoints for updating goal constraints and hot-editing goal objectives. The agent reads this text on every
iteration, so it passes the same risk gate as a chat message.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.agent.goals.goal_registry import GoalRegistry
from app.services.risk.ingress import screen_user_text

logger = logging.getLogger(__name__)

constraints_router = APIRouter()

MAX_OBJECTIVE_LENGTH = 2000


class ConstraintsUpdateRequest(BaseModel):
    constraints: list[str]


class ObjectiveUpdateRequest(BaseModel):
    objective: str


async def _reject_if_held(text: str, session_id: str) -> None:
    """Refuse goal text that a risk rule holds."""
    if await screen_user_text(text, session_id=session_id) is not None:
        raise HTTPException(status_code=400, detail="Text held by a risk rule")


@constraints_router.put("/{session_id}/constraints")
async def update_goal_constraints(session_id: str, request: ConstraintsUpdateRequest) -> dict[str, object]:
    """Set or replace constraints on the latest goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No goal found for this session")

    filtered = [c for c in request.constraints if c.strip()]
    await _reject_if_held("\n".join(filtered), session_id)
    updated = await provider.update_constraints(goal.goal_id, filtered)
    return {"status": "success", "constraints": updated.constraints}


@constraints_router.get("/{session_id}/constraints")
async def get_goal_constraints(session_id: str) -> dict[str, object]:
    """Get constraints for the latest goal in a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No goal found for this session")

    return {"constraints": goal.constraints}


@constraints_router.patch("/{session_id}/objective")
async def update_goal_objective(session_id: str, request: ObjectiveUpdateRequest) -> dict[str, object]:
    """Update the objective of the latest goal and inject a steering message."""
    objective = request.objective.strip()
    if not objective:
        raise HTTPException(status_code=400, detail="Objective cannot be empty")
    if len(objective) > MAX_OBJECTIVE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Objective exceeds {MAX_OBJECTIVE_LENGTH} characters")
    await _reject_if_held(objective, session_id)

    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No goal found for this session")

    try:
        updated = await provider.update_objective(goal.goal_id, objective)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    from myrm_agent_harness.agent.goals.steering_prompts import build_objective_updated_steering_message

    from app.services.agent.steering import SteeringRegistry

    steering_msg = build_objective_updated_steering_message(updated)
    steered = SteeringRegistry.steer(session_id, steering_msg)

    return {
        "status": "success",
        "goal": updated.to_dict(),
        "steered": steered,
    }


__all__ = [
    "ConstraintsUpdateRequest",
    "ObjectiveUpdateRequest",
    "constraints_router",
    "get_goal_constraints",
    "update_goal_constraints",
    "update_goal_objective",
]
