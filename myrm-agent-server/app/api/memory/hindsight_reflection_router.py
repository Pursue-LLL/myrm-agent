"""
[POS] app/api/memory/hindsight_reflection_router.py
[INPUT] app/schemas/hindsight_reflection.py, app/services/memory/hindsight_reflection_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.schemas.hindsight_reflection import (
    HindsightRuleResponse,
    PreExecutionWarningQuery,
    PreExecutionWarningsListResponse,
    ReflectionBufferStatsResponse,
    ReflectTaskFailureRequest,
    ReflectTaskFailureResponse,
)
from app.services.memory.hindsight_reflection_service import (
    get_hindsight_reflection_service,
)

router = APIRouter(prefix="/hindsight", tags=["memory-hindsight-reflection"])


@router.post(
    "/reflect",
    response_model=ReflectTaskFailureResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Scrub failure trajectory and extract counterfactual reflection rule",
)
def reflect_task_failure(
    req: ReflectTaskFailureRequest,
) -> ReflectTaskFailureResponse:
    """Analyze failed task turns, identify root-cause error, and register preventive rule."""
    service = get_hindsight_reflection_service()
    return service.reflect_and_record(req)


@router.post(
    "/warnings",
    response_model=PreExecutionWarningsListResponse,
    summary="Match proactive pre-execution warnings for upcoming task",
)
def get_pre_execution_warnings(
    req: PreExecutionWarningQuery,
) -> PreExecutionWarningsListResponse:
    """Retrieve historical cautionary guidelines to prevent repeated failure modes."""
    service = get_hindsight_reflection_service()
    return service.get_warnings(req)


@router.get(
    "/rules",
    response_model=list[HindsightRuleResponse],
    summary="List all registered hindsight rules",
)
def list_hindsight_rules() -> list[HindsightRuleResponse]:
    """Fetch all actionable failure prevention rules retained in memory."""
    service = get_hindsight_reflection_service()
    return service.get_rules()


@router.get(
    "/stats",
    response_model=ReflectionBufferStatsResponse,
    summary="Get hindsight reflection buffer telemetry",
)
def get_buffer_stats() -> ReflectionBufferStatsResponse:
    """Retrieve metrics on retained rules, hit count, and average confidence."""
    service = get_hindsight_reflection_service()
    return service.get_stats()
