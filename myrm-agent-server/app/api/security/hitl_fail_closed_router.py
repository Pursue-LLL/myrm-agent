"""API router for HITL Approval Fail-Closed Safety Gate & Invariant Secondary Guard.

[INPUT]
- HitlEvaluateExecutionRequest, SecondaryGuardCheckRequest payloads.

[OUTPUT]
- JSON responses with HitlExecutionVerdictDto and SecondaryGuardCheckDto.

[POS]
- Security router mounted under /security/hitl-fail-closed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.hitl_fail_closed import (
    HitlEvaluateExecutionRequest,
    HitlExecutionVerdictDto,
    SecondaryGuardCheckDto,
    SecondaryGuardCheckRequest,
)
from app.services.security.hitl_fail_closed_service import (
    HitlFailClosedService,
    get_hitl_fail_closed_service,
)

router = APIRouter(prefix="/hitl-fail-closed", tags=["hitl-fail-closed"])


@router.post("/evaluate", response_model=HitlExecutionVerdictDto)
async def evaluate_hitl_execution(
    request: HitlEvaluateExecutionRequest,
    service: HitlFailClosedService = Depends(get_hitl_fail_closed_service),
) -> HitlExecutionVerdictDto:
    """Evaluate tool execution request through two-phase fail-closed gating."""
    return service.evaluate_execution(request)


@router.post("/verify-guard", response_model=SecondaryGuardCheckDto)
async def verify_secondary_guard(
    request: SecondaryGuardCheckRequest,
    service: HitlFailClosedService = Depends(get_hitl_fail_closed_service),
) -> SecondaryGuardCheckDto:
    """Inspect invariant secondary guard constraints directly."""
    return service.verify_secondary_guard(request)
