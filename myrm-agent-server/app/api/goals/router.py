"""Goal HTTP API endpoints.

[INPUT]
- app.services.agent.goal_registry::GoalRegistry (POS: Goal registry)
- myrm_agent_harness.agent.goals.types::GoalStatus (POS: Goal status enum)

[OUTPUT]
- router: APIRouter for goal endpoints.

[POS]
Provides HTTP endpoints for the frontend to pause, resume, and clear goals.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.core.features import get_features
from pydantic import BaseModel

from app.services.agent.goal_registry import GoalRegistry

logger = logging.getLogger(__name__)


def verify_goals_enabled() -> None:
    feature_set = get_features()
    if not feature_set.enabled("goals_system"):
        raise HTTPException(status_code=403, detail="Goals system is disabled via Feature Gate")


router = APIRouter(prefix="/goals", tags=["goals"], dependencies=[Depends(verify_goals_enabled)])


class GoalStatusUpdateRequest(BaseModel):
    action: str  # "pause", "resume", "cancel", "approve", "reject"


class GoalBudgetUpdateRequest(BaseModel):
    additional_tokens: int


class SubgoalAddRequest(BaseModel):
    text: str


@router.post("/{session_id}/subgoals")
async def add_goal_subgoal(session_id: str, request: SubgoalAddRequest) -> dict[str, object]:
    """Add a new subgoal to the active goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No active goal found for this session")

    try:
        subgoal = await provider.add_subgoal(goal.goal_id, request.text)
        return {"status": "success", "subgoal": subgoal}
    except Exception as e:
        logger.error(f"Failed to add subgoal: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{session_id}/subgoals/{index}")
async def remove_goal_subgoal(session_id: str, index: int) -> dict[str, object]:
    """Remove a subgoal by index from the active goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No active goal found for this session")

    try:
        removed = await provider.remove_subgoal(goal.goal_id, index)
        return {"status": "success", "removed": removed}
    except IndexError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Failed to remove subgoal: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/{session_id}/subgoals")
async def clear_goal_subgoals(session_id: str) -> dict[str, object]:
    """Clear all subgoals from the active goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No active goal found for this session")

    try:
        count = await provider.clear_subgoals(goal.goal_id)
        return {"status": "success", "cleared_count": count}
    except Exception as e:
        logger.error(f"Failed to clear subgoals: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{session_id}/status")
async def get_goal_status(session_id: str) -> dict[str, object]:
    """Get the current active goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        # If no provider in memory, we could try to instantiate one and check DB,
        # but for now we just return null.
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        return {"goal": None}

    result = goal.to_dict()
    pause_reason = goal.metadata.get("pause_reason")
    if pause_reason:
        result["reason"] = pause_reason
    return {"goal": result}


@router.post("/{session_id}/status")
async def update_goal_status(session_id: str, request: GoalStatusUpdateRequest) -> dict[str, str]:
    """Update the status of an active goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    # When resuming, approving, or rejecting, we need to get the latest goal, not just the strictly active one
    if request.action in ("resume", "approve", "reject"):
        goal = await provider.get_latest_goal(session_id)
    else:
        goal = await provider.get_active_goal(session_id)

    if not goal:
        raise HTTPException(status_code=404, detail="No active goal found for this session")

    try:
        if request.action == "pause":
            await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
        elif request.action == "resume":
            if hasattr(provider, "resume_goal"):
                await provider.resume_goal(goal.goal_id, reset_turns=True)
            else:
                await provider.update_status(goal.goal_id, GoalStatus.ACTIVE)
        elif request.action == "cancel":
            await provider.update_status(goal.goal_id, GoalStatus.CANCELLED)
        elif request.action == "approve":
            await provider.update_status(goal.goal_id, GoalStatus.COMPLETE)
        elif request.action == "reject":
            await provider.reset_verification_retries(goal.goal_id)
            await provider.update_status(goal.goal_id, GoalStatus.ACTIVE)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid action: {request.action}")

        updated = await provider.get_goal(goal.goal_id)
        return {
            "status": "success",
            "goal_id": goal.goal_id,
            "new_status": updated.status.value if updated else "unknown",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{session_id}/plan")
async def get_goal_plan(session_id: str) -> dict[str, object]:
    """Get the current plan for a session's goal."""
    try:
        from myrm_agent_harness.agent.sub_agents.planner import PlannerStorage

        from app.platform_utils import get_storage_provider

        storage_provider = get_storage_provider()
        planner_storage = PlannerStorage(storage_provider, prefix="planner_")
        plan = await planner_storage.load_plan()

        if not plan:
            return {"plan": None}

        return {"plan": plan.model_dump()}
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Failed to get goal plan: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{session_id}/approve_plan")
async def approve_goal_plan(session_id: str) -> dict[str, str]:
    """Approve the plan and resume the goal execution."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No goal found for this session")

    if goal.status != GoalStatus.PENDING_APPROVAL:
        raise HTTPException(
            status_code=400,
            detail=f"Goal is not pending approval (current status: {goal.status.value})",
        )

    try:
        # Update status back to ACTIVE
        await provider.update_status(goal.goal_id, GoalStatus.ACTIVE)

        # Resume the harness state machine
        # We use the standard chat resume mechanism by sending a Command
        import asyncio

        from app.services.agent.stream_handler import stream_agent_run
        from langgraph.types import Command

        # Fire and forget the resume command
        # The frontend should already be listening to the SSE stream
        asyncio.create_task(
            stream_agent_run(
                session_id=session_id,
                query=Command(resume="approved"),
                message_id=f"resume_{goal.goal_id}",
                context={"session_id": session_id},
            )
        )

        return {"status": "success", "goal_id": goal.goal_id}
    except Exception as e:
        import logging

        logging.getLogger(__name__).error(f"Failed to approve goal plan: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/{session_id}/budget")
async def update_goal_budget(session_id: str, request: GoalBudgetUpdateRequest) -> dict[str, object]:
    """Add tokens to the budget of the latest goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    goal = await provider.get_latest_goal(session_id)
    if not goal:
        raise HTTPException(status_code=404, detail="No goal found for this session")

    if request.additional_tokens <= 0:
        raise HTTPException(status_code=400, detail="Additional tokens must be positive")

    try:
        updated_goal = await provider.update_budget(goal.goal_id, request.additional_tokens)
        return {
            "status": "success",
            "goal_id": updated_goal.goal_id,
            "new_budget": (
                {
                    "max_tokens": updated_goal.budget.max_tokens,
                    "max_usd": updated_goal.budget.max_usd,
                    "max_time_seconds": updated_goal.budget.max_time_seconds,
                    "max_turns": updated_goal.budget.max_turns,
                    "convergence_window": updated_goal.budget.convergence_window,
                    "loop_on_pause": updated_goal.budget.loop_on_pause,
                    "max_loop_restarts": updated_goal.budget.max_loop_restarts,
                }
                if updated_goal.budget
                else None
            ),
        }
    except Exception as e:
        import traceback

        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/{session_id}/dag")
async def get_goal_dag(session_id: str) -> dict[str, object]:
    """Get the DAG structure of the current plan."""
    try:
        from myrm_agent_harness.agent.sub_agents.planner import PlannerStorage

        from app.platform_utils import get_storage_provider

        storage_provider = get_storage_provider()
        planner_storage = PlannerStorage(storage_provider, prefix="planner_")
        plan = await planner_storage.load_plan()

        if not plan:
            return {"nodes": [], "edges": []}

        nodes = []
        edges = []

        for step in plan.steps:
            nodes.append(
                {
                    "id": step.step_id,
                    "data": {
                        "label": step.description,
                        "status": step.status,
                        "expected_output": step.expected_output,
                        "risk_level": step.risk_level,
                    },
                }
            )
            for dep in step.dependencies:
                edges.append(
                    {
                        "id": f"e_{dep}_{step.step_id}",
                        "source": dep,
                        "target": step.step_id,
                    }
                )

        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.error(f"Failed to get goal DAG: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e


# ---------------------------------------------------------------------------
# Queue endpoints
# ---------------------------------------------------------------------------


class QueueReorderRequest(BaseModel):
    ordered_goal_ids: list[str]


@router.get("/{session_id}/queue")
async def get_goal_queue(session_id: str) -> dict[str, object]:
    """Get all queued goals for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    queued = await provider.get_queued_goals(session_id)
    return {"queue": [g.to_dict() for g in queued]}


@router.delete("/{session_id}/queue/{goal_id}")
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


@router.post("/{session_id}/queue/reorder")
async def reorder_goal_queue(session_id: str, request: QueueReorderRequest) -> dict[str, str]:
    """Reorder the goal queue by providing ordered goal IDs."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    await provider.reorder_queue(session_id, request.ordered_goal_ids)
    return {"status": "success"}


# ---------------------------------------------------------------------------
# Constraints endpoints
# ---------------------------------------------------------------------------


class ConstraintsUpdateRequest(BaseModel):
    constraints: list[str]


@router.put("/{session_id}/constraints")
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
    updated = await provider.update_constraints(goal.goal_id, filtered)
    return {"status": "success", "constraints": updated.constraints}


@router.get("/{session_id}/constraints")
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


# ---------------------------------------------------------------------------
# Objective hot-edit endpoint
# ---------------------------------------------------------------------------

MAX_OBJECTIVE_LENGTH = 2000


class ObjectiveUpdateRequest(BaseModel):
    objective: str


@router.patch("/{session_id}/objective")
async def update_goal_objective(session_id: str, request: ObjectiveUpdateRequest) -> dict[str, object]:
    """Update the objective of the latest goal and inject a steering message."""
    objective = request.objective.strip()
    if not objective:
        raise HTTPException(status_code=400, detail="Objective cannot be empty")
    if len(objective) > MAX_OBJECTIVE_LENGTH:
        raise HTTPException(status_code=400, detail=f"Objective exceeds {MAX_OBJECTIVE_LENGTH} characters")

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

    from app.services.agent.steering_registry import SteeringRegistry

    steering_msg = build_objective_updated_steering_message(updated)
    steered = SteeringRegistry.steer(session_id, steering_msg)

    return {
        "status": "success",
        "goal": updated.to_dict(),
        "steered": steered,
    }
