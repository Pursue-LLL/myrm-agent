"""API router for Task Triad Trajectory and Anti-Loop Execution Blackbox.

[INPUT]
- Internal: schemas.task_triad_trajectory, services.memory.task_triad_trajectory_service
- External: fastapi

[OUTPUT]
- router: APIRouter handling task triad milestone, dead-end, steering, and snapshot endpoints.

[POS]
Server API layer exposing long-horizon task triad memory to WebUI and runtime loop.
"""

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.task_triad_trajectory import (
    AntiLoopSnapshotResponseDTO,
    CheckActionRequestDTO,
    CheckActionResponseDTO,
    FailedAttemptItemDTO,
    MilestoneItemDTO,
    RecordFailedAttemptRequestDTO,
    RecordMilestoneRequestDTO,
    RecordUserSteeringRequestDTO,
    TaskTrajectoryBlackboxResponseDTO,
    UserSteeringItemDTO,
)
from app.services.memory.task_triad_trajectory_service import (
    get_task_triad_trajectory_service,
)

router = APIRouter(prefix="/triad-trajectory", tags=["memory-triad-trajectory"])


@router.post(
    "/milestone",
    response_model=MilestoneItemDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record verified milestone in long-horizon task",
)
def record_milestone(req: RecordMilestoneRequestDTO) -> MilestoneItemDTO:
    """Record a verified completed milestone to prevent duplicate effort."""
    service = get_task_triad_trajectory_service()
    return service.record_milestone(req)


@router.post(
    "/failed-attempt",
    response_model=FailedAttemptItemDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record dead-end failed attempt and anti-loop rule",
)
def record_failed_attempt(req: RecordFailedAttemptRequestDTO) -> FailedAttemptItemDTO:
    """Record a failed action and establish an anti-loop prohibition rule."""
    service = get_task_triad_trajectory_service()
    return service.record_failed_attempt(req)


@router.post(
    "/steering",
    response_model=UserSteeringItemDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Record dynamic in-flight user constraint instruction",
)
def record_user_steering(req: RecordUserSteeringRequestDTO) -> UserSteeringItemDTO:
    """Capture in-flight user steering instruction preventing steering loss."""
    service = get_task_triad_trajectory_service()
    return service.record_user_steering(req)


@router.post(
    "/check-action",
    response_model=CheckActionResponseDTO,
    summary="Check whether an intended action is blocked by a dead-end rule",
)
def check_action(req: CheckActionRequestDTO) -> CheckActionResponseDTO:
    """Check whether intended command or tool invocation triggers known dead ends."""
    service = get_task_triad_trajectory_service()
    return service.check_action(req)


@router.get(
    "/{task_id}/anti-loop-snapshot",
    response_model=AntiLoopSnapshotResponseDTO,
    summary="Get compact pre-prompt anti-loop snapshot for LLM injection",
)
def get_anti_loop_snapshot(
    task_id: str,
    step_hint: str = Query(default="", description="Hint or next step description"),
    max_tokens: int = Query(default=150, ge=50, le=500, description="Max token budget"),
) -> AntiLoopSnapshotResponseDTO:
    """Synthesize high-density pre-prompt snapshot adhering to strict token budget."""
    service = get_task_triad_trajectory_service()
    snapshot = service.get_anti_loop_snapshot(task_id, step_hint=step_hint, max_tokens=max_tokens)
    if not snapshot:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found in triad trajectory registry",
        )
    return snapshot


@router.get(
    "/{task_id}/blackbox",
    response_model=TaskTrajectoryBlackboxResponseDTO,
    summary="Get full task triad trajectory blackbox for audit or handoff",
)
def get_blackbox(task_id: str) -> TaskTrajectoryBlackboxResponseDTO:
    """Retrieve complete triad state trajectory for crash recovery or UI visualization."""
    service = get_task_triad_trajectory_service()
    blackbox = service.get_blackbox_trajectory(task_id)
    if not blackbox:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found in triad trajectory registry",
        )
    return blackbox
