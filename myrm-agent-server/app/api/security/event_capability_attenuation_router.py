"""
[POS] app/api/security/event_capability_attenuation_router.py
[INPUT] app.schemas.event_capability_attenuation, app.services.security.event_capability_attenuation_service
[OUTPUT] router

FastAPI router for Event-Triggered Capability Attenuation & Multi-Channel Async Approval Bridge.
Exposes REST endpoints to authenticate incoming events, manage session trust scopes,
evaluate tool permissions, create out-of-band approval tickets, and grant/consume one-time tokens.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.event_capability_attenuation import (
    ApprovalTicketResponse,
    ApproveTicketRequest,
    ApproveTicketResponse,
    CapabilityAttenuationMetricsResponse,
    ConsumeTokenRequest,
    ConsumeTokenResponse,
    CreateTicketRequest,
    EventIngestRequest,
    EventIngestResponse,
    RegisterSecretRequest,
    RejectTicketRequest,
    SessionScopeResponse,
    SessionScopeUpdateRequest,
    ToolEvaluationRequest,
    ToolEvaluationResponse,
)
from app.services.security.event_capability_attenuation_service import (
    EventCapabilityAttenuationService,
    get_event_capability_attenuation_service,
)

router = APIRouter(
    prefix="/event-attenuation",
    tags=["Event-Triggered Capability Attenuation & Async Approval Bridge"],
)


@router.post(
    "/register-secret",
    response_model=dict[str, bool],
    status_code=status.HTTP_200_OK,
    summary="Register HMAC shared secret for external event publisher",
)
def register_secret(
    request: RegisterSecretRequest,
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> dict[str, bool]:
    """Register source secret key used to verify incoming event signatures."""
    success = service.register_secret(request)
    return {"registered": success}


@router.post(
    "/ingest-event",
    response_model=EventIngestResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest external event, verify HMAC signature and bind low-trust scope",
)
def ingest_event(
    request: EventIngestRequest,
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> EventIngestResponse:
    """Validate event origin authenticity and optionally enforce session attenuation."""
    return service.ingest_event(request)


@router.post(
    "/evaluate-tool",
    response_model=ToolEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Evaluate whether requested tool can execute directly under active scope",
)
def evaluate_tool(
    request: ToolEvaluationRequest,
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> ToolEvaluationResponse:
    """Check tool permissions against read-only whitelist or trigger approval requirement."""
    return service.evaluate_tool(request)


@router.get(
    "/scope/{session_id}",
    response_model=SessionScopeResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect active trust scope for an agent session",
)
def get_session_scope(
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> SessionScopeResponse:
    """Retrieve current session trust scope (USER_INTERACTIVE, LOW_TRUST_EVENT_SCOPE, etc.)."""
    return service.get_session_scope(session_id)


@router.put(
    "/scope/{session_id}",
    response_model=SessionScopeResponse,
    status_code=status.HTTP_200_OK,
    summary="Update trust scope for an agent session",
)
def set_session_scope(
    request: SessionScopeUpdateRequest,
    session_id: str = Path(..., min_length=1, description="Session identifier"),
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> SessionScopeResponse:
    """Configure session trust scope explicitly."""
    return service.set_session_scope(session_id, request)


@router.post(
    "/tickets",
    response_model=ApprovalTicketResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create out-of-band asynchronous approval ticket for attenuated agent action",
)
def create_ticket(
    request: CreateTicketRequest,
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> ApprovalTicketResponse:
    """Generate structured ticket containing Diff payload, risk classification, and channel targets."""
    return service.create_ticket(request)


@router.get(
    "/tickets/{ticket_id}",
    response_model=ApprovalTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect status of an approval ticket",
)
def get_ticket(
    ticket_id: str = Path(..., min_length=1, description="Ticket identifier"),
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> ApprovalTicketResponse:
    """Retrieve ticket details with lazy expiry evaluation."""
    ticket = service.get_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket '{ticket_id}' not found.",
        )
    return ticket


@router.get(
    "/tickets",
    response_model=list[ApprovalTicketResponse],
    status_code=status.HTTP_200_OK,
    summary="List all pending approval tickets",
)
def list_pending_tickets(
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> list[ApprovalTicketResponse]:
    """Retrieve all tickets awaiting operator decision."""
    return service.list_pending_tickets()


@router.post(
    "/tickets/{ticket_id}/approve",
    response_model=ApproveTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Approve ticket and grant single-use execution authorization token",
)
def approve_ticket(
    request: ApproveTicketRequest,
    ticket_id: str = Path(..., min_length=1, description="Ticket identifier"),
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> ApproveTicketResponse:
    """Authorize requested action and issue single-use token."""
    res = service.approve_ticket(ticket_id, request)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot approve ticket '{ticket_id}'. It may not exist or is no longer pending.",
        )
    return res


@router.post(
    "/tickets/{ticket_id}/reject",
    response_model=ApprovalTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Reject pending approval ticket",
)
def reject_ticket(
    request: RejectTicketRequest,
    ticket_id: str = Path(..., min_length=1, description="Ticket identifier"),
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> ApprovalTicketResponse:
    """Reject ticket and prevent execution."""
    res = service.reject_ticket(ticket_id, request)
    if res is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reject ticket '{ticket_id}'. It may not exist or is no longer pending.",
        )
    return res


@router.post(
    "/consume-token",
    response_model=ConsumeTokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Consume single-use execution grant token",
)
def consume_token(
    request: ConsumeTokenRequest,
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> ConsumeTokenResponse:
    """Validate and burn single-use authorization token to execute action."""
    return service.consume_token(request)


@router.get(
    "/metrics",
    response_model=CapabilityAttenuationMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve cumulative telemetry metrics for event attenuation and async bridge",
)
def get_metrics(
    service: EventCapabilityAttenuationService = Depends(
        get_event_capability_attenuation_service
    ),
) -> CapabilityAttenuationMetricsResponse:
    """Inspect cumulative event authentications, attenuated executions, and ticket states."""
    return service.get_metrics()
