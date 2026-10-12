"""
[POS] app/api/security/live_session_credential_shield_router.py
[INPUT] app.schemas.live_session_credential_shield, app.services.security.live_session_credential_shield_service
[OUTPUT] router

FastAPI router for Live Session Out-of-Band Credential Input Shield Suite.
Exposes endpoints for out-of-band blind credential keystroke routing, screen pixel masking,
DOM tree credential redaction, and atomic handover scrubs.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.live_session_credential_shield import (
    AirlockStatusResponse,
    BlindCredentialInputEventResponse,
    CloseAirlockRequest,
    HandoverScrubRequest,
    HandoverScrubResponse,
    LiveSessionShieldMetricsResponse,
    OpenAirlockRequest,
    RedactDOMRequest,
    RedactDOMResponse,
    RegisterMaskRegionRequest,
    RouteBlindInputRequest,
    RouteBlindInputResponse,
    ScreenMaskRegionResponse,
)
from app.services.security.live_session_credential_shield_service import (
    LiveSessionCredentialShieldService,
    get_live_session_credential_shield_service,
)

router = APIRouter(
    prefix="/live-session-credential-shield",
    tags=["Live Session Out-of-Band Credential Input Shield"],
)


@router.post(
    "/airlock/open",
    response_model=AirlockStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Open an out-of-band credential airlock channel for a live session",
)
def open_airlock(
    request: OpenAirlockRequest,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> AirlockStatusResponse:
    """Establish dedicated airlock to isolate credentials during takeover."""
    return service.open_airlock(request)


@router.post(
    "/airlock/close",
    response_model=AirlockStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Close an active out-of-band credential airlock channel",
)
def close_airlock(
    request: CloseAirlockRequest,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> AirlockStatusResponse:
    """Tear down out-of-band airlock channel."""
    return service.close_airlock(request)


@router.get(
    "/airlock/{session_id}/status",
    response_model=AirlockStatusResponse,
    summary="Query active operational status of a session's airlock channel",
)
def get_airlock_status(
    session_id: str,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> AirlockStatusResponse:
    """Check whether airlock channel is OPEN, CLOSED, or BLIND_ROUTING."""
    return service.get_airlock_status(session_id)


@router.post(
    "/airlock/route-blind-input",
    response_model=RouteBlindInputResponse,
    status_code=status.HTTP_200_OK,
    summary="Route sensitive keystrokes out-of-band without leaking text to agent observation",
)
def route_blind_input(
    request: RouteBlindInputRequest,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> RouteBlindInputResponse:
    """Dispatch keystrokes directly to target DOM element and emit safe blind descriptor."""
    return service.route_blind_input(request)


@router.get(
    "/airlock/{session_id}/events",
    response_model=list[BlindCredentialInputEventResponse],
    summary="List historical blind input audit events for a session",
)
def list_session_blind_events(
    session_id: str,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> list[BlindCredentialInputEventResponse]:
    """Inspect routed blind input audit log without exposing confidential characters."""
    return service.list_session_blind_events(session_id)


@router.post(
    "/masking/regions",
    response_model=ScreenMaskRegionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a screen pixel coordinate bounding box for opaque masking",
)
def register_mask_region(
    request: RegisterMaskRegionRequest,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> ScreenMaskRegionResponse:
    """Designate screen coordinate region to obscure sensitive inputs from screenshots."""
    return service.register_mask_region(request)


@router.get(
    "/masking/regions/{session_id}",
    response_model=list[ScreenMaskRegionResponse],
    summary="List registered screen pixel mask regions for a session",
)
def list_mask_regions(
    session_id: str,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> list[ScreenMaskRegionResponse]:
    """Retrieve all bounding box mask areas for active session."""
    return service.list_mask_regions(session_id)


@router.post(
    "/redaction/dom",
    response_model=RedactDOMResponse,
    status_code=status.HTTP_200_OK,
    summary="Sanitize password input values and technological tokens from DOM HTML",
)
def redact_dom_tree(
    request: RedactDOMRequest,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> RedactDOMResponse:
    """Scrub sensitive credentials from DOM before delivering to agent observation context."""
    return service.redact_dom_tree(request)


@router.post(
    "/handover/scrub",
    response_model=HandoverScrubResponse,
    status_code=status.HTTP_200_OK,
    summary="Atomically execute screen-DOM scrub when returning control to Agent",
)
def execute_handover_scrub(
    request: HandoverScrubRequest,
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> HandoverScrubResponse:
    """Execute complete sanitization workflow when user finishes manual takeover."""
    return service.execute_handover_scrub(request)


@router.get(
    "/metrics",
    response_model=LiveSessionShieldMetricsResponse,
    summary="Get cumulative operational metrics for live session credential shield suite",
)
def get_metrics(
    service: LiveSessionCredentialShieldService = Depends(
        get_live_session_credential_shield_service
    ),
) -> LiveSessionShieldMetricsResponse:
    """Inspect metrics on blind inputs routed, screen masks applied, and injections mitigated."""
    return service.get_metrics()
