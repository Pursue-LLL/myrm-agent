"""API router for Agent Authority ChangeGuard review decision lanes and evidence hardening.

[INPUT]
- EvaluateChangesRequest.

[OUTPUT]
- EvaluateChangesResponse, ChangeGuardConfigSummary.

[POS]
- Security router mounted under /security/change-guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.change_guard import (
    ChangeGuardConfigSummary,
    EvaluateChangesRequest,
    EvaluateChangesResponse,
)
from app.services.security.change_guard_service import (
    ChangeGuardService,
    get_change_guard_service,
)

router = APIRouter(prefix="/change-guard", tags=["change-guard"])


@router.post("/evaluate", response_model=EvaluateChangesResponse)
async def evaluate_changes(
    request: EvaluateChangesRequest,
    service: ChangeGuardService = Depends(get_change_guard_service),
) -> EvaluateChangesResponse:
    """Evaluate change findings against separated review lanes (Lane A vs Lane B) and authority gates."""
    return service.evaluate_changes(request)


@router.get("/config", response_model=ChangeGuardConfigSummary)
async def get_config_summary(
    service: ChangeGuardService = Depends(get_change_guard_service),
) -> ChangeGuardConfigSummary:
    """Retrieve supported ChangeGuard taxonomy, change classes, and rule prefixes."""
    return service.get_config_summary()
