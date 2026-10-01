"""Goal HTTP API endpoints.

[INPUT]
- app.services.agent.goals.goal_registry::GoalRegistry (POS: Goal registry)
- myrm_agent_harness.agent.goals.types::GoalStatus (POS: Goal status enum)

[OUTPUT]
- router: APIRouter for goal endpoints.

[POS]
Provides HTTP endpoints for the frontend to pause, resume, and clear goals.
"""

import logging
from typing import TYPE_CHECKING, Annotated

from fastapi import APIRouter, Depends, HTTPException
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.agent.goals.types import GoalStatus
from myrm_agent_harness.core.features import get_features
from pydantic import BaseModel

from app.api.dependencies import get_optional_llm_for_user
from app.services.agent.goals.goal_registry import GoalRegistry

from .constraints import (
    ConstraintsUpdateRequest,
    ObjectiveUpdateRequest,
    constraints_router,
    get_goal_constraints,
    update_goal_constraints,
    update_goal_objective,
)
from .plan import get_goal_dag, get_goal_plan, plan_router
from .queue import QueueReorderRequest, get_goal_queue, queue_router

if TYPE_CHECKING:
    from myrm_agent_harness.agent.goals.types import Goal

logger = logging.getLogger(__name__)


def verify_goals_enabled() -> None:
    feature_set = get_features()
    if not feature_set.enabled("goals_system"):
        raise HTTPException(status_code=403, detail="Goals system is disabled via Feature Gate")


router = APIRouter(prefix="/goals", tags=["goals"], dependencies=[Depends(verify_goals_enabled)])
router.include_router(plan_router)
router.include_router(queue_router)
router.include_router(constraints_router)


_NON_TERMINAL_STATUSES: frozenset[GoalStatus] = frozenset(
    {
        GoalStatus.ACTIVE,
        GoalStatus.PAUSED,
        GoalStatus.PENDING_APPROVAL,
        GoalStatus.BUDGET_LIMITED,
        GoalStatus.NEEDS_HUMAN_REVIEW,
        GoalStatus.QUEUED,
        GoalStatus.WAIT,
    }
)


def _serialize_goal(goal: "Goal") -> dict[str, object]:
    return {
        "goal_id": goal.goal_id,
        "session_id": goal.session_id,
        "objective": goal.objective,
        "status": goal.status.value,
        "tokens_used": goal.tokens_used,
        "created_at": goal.created_at.isoformat(),
    }


@router.get("/active")
async def list_active_goals() -> dict[str, object]:
    """List all non-terminal goals across all sessions from in-memory GoalRegistry."""
    results: list[dict[str, object]] = []

    with GoalRegistry._lock:
        session_ids = list(GoalRegistry._providers.keys())

    for sid in session_ids:
        provider = GoalRegistry.get_provider(sid)
        if not provider:
            continue
        try:
            goal = await provider.get_latest_goal(sid)
            if goal and goal.status in _NON_TERMINAL_STATUSES:
                results.append(_serialize_goal(goal))
        except Exception as e:
            logger.debug("Failed to get goal for session %s: %s", sid, e)

    return {"goals": results, "count": len(results)}


class GoalStatusUpdateRequest(BaseModel):
    action: str  # "pause", "resume", "cancel", "approve", "reject", "wait", "unwait"
    note: str | None = None
    wait_reason: str | None = None


class GoalDraftRequest(BaseModel):
    objective: str
    locale: str | None = None


class GoalDraftResponse(BaseModel):
    constraints: list[str]
    acceptance_criteria: list[dict[str, object]]
    ui_summary: str


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
        raise HTTPException(status_code=500, detail="Failed to add subgoal") from e


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
        raise HTTPException(status_code=500, detail="Failed to remove subgoal") from e


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
        raise HTTPException(status_code=500, detail="Failed to clear subgoals") from e


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
    wait_reason = goal.metadata.get("wait_reason")
    if wait_reason:
        result["wait_reason"] = wait_reason
    deliverables = goal.metadata.get("deliverables")
    if deliverables:
        result["deliverables"] = deliverables
    return {"goal": result}


@router.post("/{session_id}/status")
async def update_goal_status(session_id: str, request: GoalStatusUpdateRequest) -> dict[str, str]:
    """Update the status of an active goal for a session."""
    provider = GoalRegistry.get_provider(session_id)
    if not provider:
        from myrm_agent_harness.agent.goals.manager import GoalManager

        from app.platform_utils import get_storage_provider

        provider = GoalManager(get_storage_provider())

    # When resuming, approving, rejecting, or unwaiting, use latest goal (may be WAIT/PAUSED)
    if request.action in ("resume", "approve", "reject", "unwait"):
        goal = await provider.get_latest_goal(session_id)
    elif request.action == "wait":
        goal = await provider.get_active_goal(session_id)
    else:
        goal = await provider.get_active_goal(session_id)

    if not goal and request.action == "unwait":
        goal = await provider.get_latest_goal(session_id)

    if not goal:
        raise HTTPException(status_code=404, detail="No active goal found for this session")

    try:
        if request.action == "pause":
            await provider.update_status(goal.goal_id, GoalStatus.PAUSED)
            if request.note and hasattr(provider, "update_metadata"):
                await provider.update_metadata(goal.goal_id, {"pause_reason": request.note.strip()})
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
        elif request.action == "wait":
            if not hasattr(provider, "enter_wait"):
                raise HTTPException(status_code=501, detail="Wait not supported by provider")
            reason = (request.wait_reason or request.note or "Waiting for external process").strip()
            await provider.enter_wait(goal.goal_id, reason=reason)
        elif request.action == "unwait":
            if not hasattr(provider, "exit_wait"):
                raise HTTPException(status_code=501, detail="Unwait not supported by provider")
            if goal.status != GoalStatus.WAIT:
                raise HTTPException(status_code=400, detail="Goal is not in WAIT state")
            await provider.exit_wait(goal.goal_id)
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
        logger.error("Goal action failed: %s", e)
        raise HTTPException(status_code=500, detail="Goal action failed") from e


@router.post("/draft", response_model=GoalDraftResponse)
async def draft_goal(
    request: GoalDraftRequest,
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
) -> GoalDraftResponse:
    """Generate draft constraints and acceptance criteria for a goal objective."""
    from app.services.agent.goals.goal_draft import draft_goal_spec

    try:
        spec = await draft_goal_spec(
            llm,
            request.objective,
            locale=request.locale,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Goal draft generation failed: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to generate goal draft") from e

    return GoalDraftResponse(
        constraints=list(spec.get("constraints", [])),
        acceptance_criteria=list(spec.get("acceptance_criteria", [])),
        ui_summary=str(spec.get("ui_summary", "")),
    )



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
        logger.exception("Failed to update goal budget")
        raise HTTPException(status_code=500, detail="Failed to update goal budget") from e



__all__ = [
    "ConstraintsUpdateRequest",
    "GoalBudgetUpdateRequest",
    "GoalDraftRequest",
    "GoalDraftResponse",
    "GoalStatusUpdateRequest",
    "ObjectiveUpdateRequest",
    "QueueReorderRequest",
    "get_goal_constraints",
    "get_goal_dag",
    "get_goal_plan",
    "get_goal_queue",
    "router",
    "update_goal_budget",
    "update_goal_constraints",
    "update_goal_objective",
]
