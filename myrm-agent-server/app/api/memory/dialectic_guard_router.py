"""FastAPI router for Dialectic Liveness Guard & Stale Pivot Discard (Item 116).

[POS]
app/api/memory/dialectic_guard_router.py

[INPUT]
- app.schemas.dialectic_guard, app.services.memory.dialectic_guard_service

[OUTPUT]
- router
"""


from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from app.schemas.dialectic_guard import (
    ConsumePendingRequest,
    ConsumePendingResponse,
    DialecticAuditLogDTO,
    LivenessTelemetryDTO,
    NotifyMutationRequest,
    NotifyMutationResponse,
    ShouldTriggerRequest,
    ShouldTriggerResponse,
    SubmitResultRequest,
    SubmitResultResponse,
)
from app.services.memory.dialectic_guard_service import (
    DialecticGuardService,
    get_dialectic_guard_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/dialectic-guard",
    tags=["Memory - Dialectic Liveness Guard"],
)


@router.post(
    "/should-trigger",
    response_model=ShouldTriggerResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate dialectic trigger conditions and allocate cycle token",
)
async def evaluate_should_trigger(
    payload: ShouldTriggerRequest,
    service: Annotated[DialecticGuardService, Depends(get_dialectic_guard_service)],
) -> ShouldTriggerResponse:
    """Evaluate whether background dialectic inference should launch."""
    return service.should_trigger(payload)


@router.post(
    "/submit-result",
    response_model=SubmitResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Submit dialectic inference result with orphan zombie token rejection",
)
async def submit_result(
    payload: SubmitResultRequest,
    service: Annotated[DialecticGuardService, Depends(get_dialectic_guard_service)],
) -> SubmitResultResponse:
    """Submit completed inference result from background task."""
    return service.submit_result(payload)


@router.post(
    "/consume-pending",
    response_model=ConsumePendingResponse,
    status_code=status.HTTP_200_OK,
    summary="Consume pending result or invalidate if conversational pivot occurred",
)
async def consume_pending_result(
    payload: ConsumePendingRequest,
    service: Annotated[DialecticGuardService, Depends(get_dialectic_guard_service)],
) -> ConsumePendingResponse:
    """Consume staged dialectic result or discard on conversational pivot."""
    return service.consume_pending_result(payload)


@router.post(
    "/notify-mutation",
    response_model=NotifyMutationResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset backoff streak immediately on critical mutation event",
)
async def notify_mutation(
    payload: NotifyMutationRequest,
    service: Annotated[DialecticGuardService, Depends(get_dialectic_guard_service)],
) -> NotifyMutationResponse:
    """Reset exponential backoff to baseline cadence on critical mutation."""
    return service.notify_mutation(payload)


@router.get(
    "/telemetry/{session_id}",
    response_model=LivenessTelemetryDTO,
    status_code=status.HTTP_200_OK,
    summary="Get liveness telemetry snapshot for a session",
)
async def get_telemetry(
    session_id: str,
    current_turn: Annotated[int, Query(ge=0)] = 0,
    service: Annotated[DialecticGuardService, Depends(get_dialectic_guard_service)] = None,  # type: ignore[assignment]
) -> LivenessTelemetryDTO:
    """Retrieve liveness telemetry and slot status."""
    return service.get_telemetry(session_id, current_turn)


@router.get(
    "/audits/{session_id}",
    response_model=list[DialecticAuditLogDTO],
    status_code=status.HTTP_200_OK,
    summary="Get full audit log history for a session",
)
async def get_audit_logs(
    session_id: str,
    service: Annotated[DialecticGuardService, Depends(get_dialectic_guard_service)] = None,  # type: ignore[assignment]
) -> list[DialecticAuditLogDTO]:
    """Retrieve immutable audit trail entries."""
    return service.get_audit_logs(session_id)
