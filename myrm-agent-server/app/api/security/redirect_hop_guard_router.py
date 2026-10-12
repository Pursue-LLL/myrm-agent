"""API Router for Redirect Private Address Hop Revalidation Suite.

[INPUT]
- fastapi::APIRouter, Depends, status
- app.schemas.redirect_hop_guard::(HopEvaluationRequest, HopEvaluationResponse, HopPolicyConfigRequest, HopPolicyConfigResponse, HopViolationRecordResponse, HopViolationsListResponse, HopSimulationRequest)
- app.services.security.redirect_hop_guard_service::RedirectHopGuardService

[OUTPUT]
- redirect_hop_guard_router: mounted FastAPI router

[POS]
REST API boundary for browser redirect hop revalidation and violation audit history.
Strictly avoids Any types; enforced under 400 lines limit.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.redirect_hop_guard import (
    HopEvaluationRequest,
    HopEvaluationResponse,
    HopPolicyConfigRequest,
    HopPolicyConfigResponse,
    HopSimulationRequest,
    HopViolationRecordResponse,
    HopViolationsListResponse,
)
from app.services.security.redirect_hop_guard_service import RedirectHopGuardService

redirect_hop_guard_router = APIRouter(
    prefix="/redirect-hop-guard",
    tags=["Redirect Hop Guard"],
)


def get_hop_guard_service() -> RedirectHopGuardService:
    """Dependency provider for RedirectHopGuardService."""
    return RedirectHopGuardService.get_instance()


@redirect_hop_guard_router.post(
    "/evaluate",
    response_model=HopEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate an outgoing hop or redirect target URL",
)
async def evaluate_hop(
    request: HopEvaluationRequest,
    service: RedirectHopGuardService = Depends(get_hop_guard_service),
) -> HopEvaluationResponse:
    """Check whether a target URL violates private network or cloud metadata boundaries."""
    return service.evaluate_hop(request)


@redirect_hop_guard_router.get(
    "/policy",
    response_model=HopPolicyConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Get active redirect hop policy configuration",
)
async def get_policy(
    service: RedirectHopGuardService = Depends(get_hop_guard_service),
) -> HopPolicyConfigResponse:
    """Retrieve current policy settings for hop revalidation."""
    return service.get_policy()


@redirect_hop_guard_router.put(
    "/policy",
    response_model=HopPolicyConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Update redirect hop policy configuration",
)
async def update_policy(
    request: HopPolicyConfigRequest,
    service: RedirectHopGuardService = Depends(get_hop_guard_service),
) -> HopPolicyConfigResponse:
    """Update policy configurations such as private network permission and tab resets."""
    return service.update_policy(request)


@redirect_hop_guard_router.post(
    "/simulate-violation",
    response_model=HopViolationRecordResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Simulate and log a redirect hop violation event",
)
async def simulate_violation(
    request: HopSimulationRequest,
    service: RedirectHopGuardService = Depends(get_hop_guard_service),
) -> HopViolationRecordResponse:
    """Simulate a hop violation event for testing and monitoring pipelines."""
    return service.simulate_violation(request)


@redirect_hop_guard_router.get(
    "/violations",
    response_model=HopViolationsListResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve recorded hop violation audit events",
)
async def get_violations(
    service: RedirectHopGuardService = Depends(get_hop_guard_service),
) -> HopViolationsListResponse:
    """List recent hop interception and about:blank reset audit records."""
    return service.get_violations()


@redirect_hop_guard_router.delete(
    "/violations",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear recorded hop violation audit events",
)
async def clear_violations(
    service: RedirectHopGuardService = Depends(get_hop_guard_service),
) -> None:
    """Purge in-memory violation audit history."""
    service.clear_violations()
