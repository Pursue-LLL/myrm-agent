"""
[POS] app/api/security/browser_human_handoff_router.py
[INPUT] fastapi, app.schemas.browser_human_handoff, app.services.security.browser_human_handoff_service
[OUTPUT] router

FastAPI router for Default Captcha & Confirm Screen Human Handoff Gate Suite.
Exposes endpoints for page safety inspection, mutual-exclusion browser profile leases,
and human intervention lifecycle.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.browser_human_handoff import (
    AcquireBrowserLeaseRequest,
    BrowserHumanHandoffMetricsResponse,
    BrowserProfileLeaseResponse,
    HandoffInterceptionResponse,
    InspectPageSafetyRequest,
    InspectPageSafetyResponse,
    ReleaseBrowserLeaseRequest,
    ResolveHandoffRequest,
)
from app.services.security.browser_human_handoff_service import (
    BrowserHumanHandoffService,
    get_browser_human_handoff_service,
)

router = APIRouter(
    prefix="/browser-human-handoff",
    tags=["Default Captcha & Confirm Screen Human Handoff"],
)


@router.post(
    "/inspect-page-safety",
    response_model=InspectPageSafetyResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect DOM markup for anti-bot captchas, confirmation screens, or empty corruptions",
)
def inspect_page_safety(
    request: InspectPageSafetyRequest,
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> InspectPageSafetyResponse:
    """Inspect page DOM and determine whether automation must suspend for human takeover."""
    return service.inspect_page_safety(request)


@router.post(
    "/resolve-handoff",
    response_model=HandoffInterceptionResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve a pending handoff gate after human operator intervention",
)
def resolve_handoff(
    request: ResolveHandoffRequest,
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> HandoffInterceptionResponse:
    """Mark a pending captcha challenge or confirmation screen resolved by a human operator."""
    try:
        return service.resolve_handoff(request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/pending-handoffs",
    response_model=list[HandoffInterceptionResponse],
    status_code=status.HTTP_200_OK,
    summary="List all browser screens currently waiting for human intervention",
)
def list_pending_handoffs(
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> list[HandoffInterceptionResponse]:
    """Retrieve all pending handoff gates across active browser tasks."""
    return service.list_pending_handoffs()


@router.post(
    "/acquire-lease",
    response_model=BrowserProfileLeaseResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Acquire exclusive session lock on a logged-in browser profile",
)
def acquire_lease(
    request: AcquireBrowserLeaseRequest,
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> BrowserProfileLeaseResponse:
    """Acquire single-task exclusive lease lock on a browser profile."""
    try:
        return service.acquire_lease(request)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc


@router.post(
    "/release-lease",
    response_model=BrowserProfileLeaseResponse,
    status_code=status.HTTP_200_OK,
    summary="Release an exclusive browser profile lease",
)
def release_lease(
    request: ReleaseBrowserLeaseRequest,
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> BrowserProfileLeaseResponse:
    """Release an active lease and return the profile to the pool."""
    try:
        return service.release_lease(request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get(
    "/active-lease/{profile_name}",
    response_model=BrowserProfileLeaseResponse | None,
    status_code=status.HTTP_200_OK,
    summary="Query active lease on a specific browser profile",
)
def get_active_lease(
    profile_name: str,
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> BrowserProfileLeaseResponse | None:
    """Check whether a specific browser profile currently has an active non-expired lease."""
    return service.get_active_lease(profile_name)


@router.get(
    "/active-leases",
    response_model=list[BrowserProfileLeaseResponse],
    status_code=status.HTTP_200_OK,
    summary="List all currently active browser profile leases",
)
def list_active_leases(
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> list[BrowserProfileLeaseResponse]:
    """Retrieve all valid non-expired browser profile leases."""
    return service.list_active_leases()


@router.get(
    "/metrics",
    response_model=BrowserHumanHandoffMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get operational metrics for browser human handoffs and leases",
)
def get_metrics(
    service: BrowserHumanHandoffService = Depends(get_browser_human_handoff_service),
) -> BrowserHumanHandoffMetricsResponse:
    """Retrieve cumulative statistics on handoffs, whiteouts, and profile leases."""
    return service.get_metrics()
