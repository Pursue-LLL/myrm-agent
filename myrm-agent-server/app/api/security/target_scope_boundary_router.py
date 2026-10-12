"""
[POS] app/api/security/target_scope_boundary_router.py
[INPUT] fastapi, app.schemas.target_scope_boundary, app.services.security.target_scope_boundary_service
[OUTPUT] router

FastAPI router for Strict Target Scope Authorization & Egress Boundary Suite.
Exposes endpoints for Rules of Engagement (ROE) contract configuration, destination scope
verification, emergency kill-switch circuit breaker, and boundary metrics.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.target_scope_boundary import (
    KillSwitchStatusResponse,
    ScopeVerificationResponse,
    SetContractRequest,
    TargetScopeContractResponse,
    TargetScopeMetricsResponse,
    VerifyTargetRequest,
)
from app.services.security.target_scope_boundary_service import (
    TargetScopeBoundaryService,
    get_target_scope_boundary_service,
)

router = APIRouter(
    prefix="/target-scope-boundary",
    tags=["Strict Target Scope Authorization & Egress Boundary"],
)


@router.post(
    "/contracts",
    response_model=TargetScopeContractResponse,
    status_code=status.HTTP_200_OK,
    summary="Register and activate an ROE target scope authorization contract",
)
def set_contract(
    request: SetContractRequest,
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> TargetScopeContractResponse:
    """Set active rules of engagement scope contract."""
    return service.set_contract(request)


@router.get(
    "/contracts/active",
    response_model=TargetScopeContractResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Retrieve active ROE target scope authorization contract",
)
def get_active_contract(
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> TargetScopeContractResponse | None:
    """Get currently active ROE contract if configured."""
    return service.get_active_contract()


@router.delete(
    "/contracts/active",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear active ROE contract",
)
def clear_contract(
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> None:
    """Deactivate and clear current contract."""
    service.clear_contract()


@router.post(
    "/verify",
    response_model=ScopeVerificationResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify outbound destination host against active ROE scope and kill-switch",
)
def verify_target(
    request: VerifyTargetRequest,
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> ScopeVerificationResponse:
    """Perform pre-flight scope and metadata boundary verification on target destination."""
    return service.verify_target(request)


@router.post(
    "/kill-switch/activate",
    response_model=KillSwitchStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Activate emergency kill-switch to immediately halt all external scans",
)
def activate_kill_switch(
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> KillSwitchStatusResponse:
    """Engage emergency kill-switch circuit breaker."""
    return service.activate_kill_switch()


@router.post(
    "/kill-switch/reset",
    response_model=KillSwitchStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Reset emergency kill-switch to restore standard ROE policy evaluation",
)
def reset_kill_switch(
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> KillSwitchStatusResponse:
    """Disengage emergency kill-switch."""
    return service.reset_kill_switch()


@router.get(
    "/kill-switch/status",
    response_model=KillSwitchStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Query current emergency kill-switch state",
)
def get_kill_switch_status(
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> KillSwitchStatusResponse:
    """Check whether kill-switch is active."""
    return service.get_kill_switch_status()


@router.get(
    "/metrics",
    response_model=TargetScopeMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve cumulative metrics for target scope verifications and egress actions",
)
def get_metrics(
    service: TargetScopeBoundaryService = Depends(get_target_scope_boundary_service),
) -> TargetScopeMetricsResponse:
    """Get metrics tracking checks, blocks, metadata attempts, and kill-switch triggers."""
    return service.get_metrics()
