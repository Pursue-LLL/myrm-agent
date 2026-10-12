"""
[POS] app/api/security/data_sovereignty_watchdog_router.py
[INPUT] app.schemas.data_sovereignty_watchdog, app.services.security.data_sovereignty_watchdog_service
[OUTPUT] router

FastAPI router for Private Sandbox Data Sovereignty & Sub-Intrusive Watchdog Suite.
Exposes endpoints for private volume data sovereignty sealing, anti-annoyance card gating,
and high-stakes action human consent ticketing.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.data_sovereignty_watchdog import (
    ConsentDecisionRequest,
    CreateConsentTicketRequest,
    DataSovereigntyWatchdogMetricsResponse,
    EvaluateSuggestionRequest,
    HighStakesConsentTicketResponse,
    IssueSovereigntySealRequest,
    SovereigntySealManifestResponse,
    SubIntrusiveNotificationCardResponse,
    VerifySovereigntySealRequest,
    VerifySovereigntySealResponse,
)
from app.services.security.data_sovereignty_watchdog_service import (
    DataSovereigntyWatchdogService,
    get_data_sovereignty_watchdog_service,
)

router = APIRouter(
    prefix="/data-sovereignty-watchdog",
    tags=["Private Sandbox Data Sovereignty & Sub-Intrusive Watchdog"],
)


@router.post(
    "/sovereignty/issue-seal",
    response_model=SovereigntySealManifestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Issue an immutable data sovereignty seal for private volume isolation",
)
def issue_sovereignty_seal(
    request: IssueSovereigntySealRequest,
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> SovereigntySealManifestResponse:
    """Issue cryptographic seal certifying zero central cloud retention."""
    return service.issue_sovereignty_seal(request)


@router.post(
    "/sovereignty/verify-seal",
    response_model=VerifySovereigntySealResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify cryptographic integrity of an issued data sovereignty seal",
)
def verify_sovereignty_seal(
    request: VerifySovereigntySealRequest,
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> VerifySovereigntySealResponse:
    """Verify seal integrity and zero-central-retention compliance."""
    return service.verify_sovereignty_seal(request)


@router.get(
    "/sovereignty/latest",
    response_model=SovereigntySealManifestResponse | None,
    summary="Retrieve most recently issued private sandbox sovereignty seal",
)
def get_latest_seal(
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> SovereigntySealManifestResponse | None:
    """Query current active sovereignty seal manifest."""
    return service.get_latest_seal()


@router.post(
    "/watchdog/evaluate",
    response_model=SubIntrusiveNotificationCardResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate suggestion against value thresholds and suppress trivial noise",
)
def evaluate_proactive_suggestion(
    request: EvaluateSuggestionRequest,
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> SubIntrusiveNotificationCardResponse:
    """Filter suggestion to avoid notification fatigue and user annoyance."""
    return service.evaluate_proactive_suggestion(request)


@router.get(
    "/watchdog/cards/active",
    response_model=list[SubIntrusiveNotificationCardResponse],
    summary="List active high-value alert notification cards",
)
def list_active_notification_cards(
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> list[SubIntrusiveNotificationCardResponse]:
    """Retrieve unsuppressed notification cards."""
    return service.list_active_notification_cards()


@router.get(
    "/watchdog/cards/all",
    response_model=list[SubIntrusiveNotificationCardResponse],
    summary="List all notification cards including suppressed noise",
)
def list_all_notification_cards(
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> list[SubIntrusiveNotificationCardResponse]:
    """Retrieve historical cards evaluated by watchdog."""
    return service.list_all_notification_cards()


@router.post(
    "/consent/create-ticket",
    response_model=HighStakesConsentTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Lock high-stakes financial mutation behind human consent ticket",
)
def create_high_stakes_consent(
    request: CreateConsentTicketRequest,
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> HighStakesConsentTicketResponse:
    """Generate one-time ticket requiring explicit user click before executing cancellation or dispute."""
    return service.create_high_stakes_consent(request)


@router.post(
    "/consent/approve",
    response_model=HighStakesConsentTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Human operator confirms and approves pending high-stakes operation",
)
def approve_consent(
    request: ConsentDecisionRequest,
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> HighStakesConsentTicketResponse:
    """Authorize execution of pending high-stakes financial ticket."""
    try:
        return service.approve_consent(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending consent ticket '{request.ticket_id}' not found.",
        ) from err


@router.post(
    "/consent/deny",
    response_model=HighStakesConsentTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Human operator rejects and cancels pending high-stakes operation",
)
def deny_consent(
    request: ConsentDecisionRequest,
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> HighStakesConsentTicketResponse:
    """Explicitly reject pending high-stakes financial ticket."""
    try:
        return service.deny_consent(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending consent ticket '{request.ticket_id}' not found.",
        ) from err


@router.get(
    "/consent/pending",
    response_model=list[HighStakesConsentTicketResponse],
    summary="List all high-stakes actions currently awaiting human consent",
)
def list_pending_consents(
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> list[HighStakesConsentTicketResponse]:
    """Retrieve queue of high-stakes actions pending operator review."""
    return service.list_pending_consents()


@router.get(
    "/metrics",
    response_model=DataSovereigntyWatchdogMetricsResponse,
    summary="Get cumulative operational metrics for data sovereignty and watchdog suite",
)
def get_metrics(
    service: DataSovereigntyWatchdogService = Depends(
        get_data_sovereignty_watchdog_service
    ),
) -> DataSovereigntyWatchdogMetricsResponse:
    """Inspect metrics on seals issued, noise suppressed, and consents approved."""
    return service.get_metrics()
