"""
[POS] app/api/agents/split_session_goal_router.py
[INPUT] fastapi, app.schemas.split_session_goal, app.services.agent.goals.split_session_goal_service
[OUTPUT] router

FastAPI router exposing Split-Session 2-Window (Window 1: Ship / Window 2: Plan) Goal templates and lifecycle transitions.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.split_session_goal import (
    AdvanceSplitSessionRequestDTO,
    CreateSplitSessionGoalRequestDTO,
    SplitSessionGoalInstanceDTO,
    SplitSessionGoalTemplateDTO,
)
from app.services.agent.goals.split_session_goal_service import (
    SplitSessionGoalService,
    get_split_session_goal_service,
)

router = APIRouter()


@router.get(
    "/goals/split-session/templates",
    response_model=list[SplitSessionGoalTemplateDTO],
    status_code=status.HTTP_200_OK,
    summary="List available Split-Session Ship/Plan goal templates",
)
def list_split_session_templates(
    service: SplitSessionGoalService = Depends(get_split_session_goal_service),
) -> list[SplitSessionGoalTemplateDTO]:
    """Retrieve collection of standard declarative 2-window templates (en/zh)."""
    return service.list_templates()


@router.post(
    "/goals/split-session",
    response_model=SplitSessionGoalInstanceDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Instantiate a new Split-Session 2-Window Goal",
)
def create_split_session_goal(
    request: CreateSplitSessionGoalRequestDTO,
    service: SplitSessionGoalService = Depends(get_split_session_goal_service),
) -> SplitSessionGoalInstanceDTO:
    """Initialize a dual-window goal instance in Window 1: Ship phase."""
    try:
        return service.create_instance(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/goals/split-session/{instance_id}",
    response_model=SplitSessionGoalInstanceDTO,
    status_code=status.HTTP_200_OK,
    summary="Get status, deliverables, and plans for a Split-Session Goal instance",
)
def get_split_session_goal(
    instance_id: str,
    service: SplitSessionGoalService = Depends(get_split_session_goal_service),
) -> SplitSessionGoalInstanceDTO:
    """Retrieve live snapshot of a 2-window goal instance."""
    inst = service.get_instance(instance_id)
    if inst is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Split-session goal instance '{instance_id}' was not found.",
        )
    return inst


@router.post(
    "/goals/split-session/{instance_id}/advance",
    response_model=SplitSessionGoalInstanceDTO,
    status_code=status.HTTP_200_OK,
    summary="Advance the split-session state machine across phase boundaries",
)
def advance_split_session_phase(
    instance_id: str,
    request: AdvanceSplitSessionRequestDTO,
    service: SplitSessionGoalService = Depends(get_split_session_goal_service),
) -> SplitSessionGoalInstanceDTO:
    """Advance phase: Window 1 Ship -> Window 1 Completed -> Window 2 Plan -> All Completed."""
    try:
        return service.advance_phase(instance_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
