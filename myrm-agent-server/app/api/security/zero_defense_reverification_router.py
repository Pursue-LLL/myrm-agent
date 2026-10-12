"""FastAPI router for Zero-Defense Error Acknowledgment and Grounded Re-Verification.

[INPUT]
- DetectDisputeRequest, CrossCheckRequest, CreateEscalationTicketRequest, ResolveEscalationTicketRequest.

[OUTPUT]
- DetectDisputeResponse, CrossCheckResponse, EscalationTicketResponse.

[POS]
- app.api.security.zero_defense_reverification_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.zero_defense_reverification import (
    CreateEscalationTicketRequest,
    CrossCheckRequest,
    CrossCheckResponse,
    DetectDisputeRequest,
    DetectDisputeResponse,
    EscalationTicketResponse,
    ResolveEscalationTicketRequest,
)
from app.services.security.zero_defense_reverification_service import (
    ZeroDefenseReVerificationService,
    get_zero_defense_reverification_service,
)

router = APIRouter(
    prefix="/security/zero-defense-reverification",
    tags=["Security - Zero-Defense Error Acknowledgment & Grounded Re-Verification"],
)


@router.post("/detect-dispute", response_model=DetectDisputeResponse)
async def detect_dispute(
    payload: DetectDisputeRequest,
    service: ZeroDefenseReVerificationService = Depends(get_zero_defense_reverification_service),
) -> DetectDisputeResponse:
    """Analyze dialogue utterance for objection, dispute, or error signals."""
    return service.detect_dispute(payload)


@router.post("/cross-check", response_model=CrossCheckResponse)
async def cross_check_grounded_evidence(
    payload: CrossCheckRequest,
    service: ZeroDefenseReVerificationService = Depends(get_zero_defense_reverification_service),
) -> CrossCheckResponse:
    """Perform side-by-side grounded verification of prior claims against evidence citations."""
    return service.cross_check(payload)


@router.post("/tickets", response_model=EscalationTicketResponse)
async def create_escalation_ticket(
    payload: CreateEscalationTicketRequest,
    service: ZeroDefenseReVerificationService = Depends(get_zero_defense_reverification_service),
) -> EscalationTicketResponse:
    """Create a domain expert escalation ticket for high-risk legal/financial disputes."""
    return service.create_escalation_ticket(payload)


@router.get("/tickets/{ticket_id}", response_model=EscalationTicketResponse)
async def get_escalation_ticket(
    ticket_id: str = Path(..., min_length=1, max_length=64, description="Escalation ticket ID"),
    service: ZeroDefenseReVerificationService = Depends(get_zero_defense_reverification_service),
) -> EscalationTicketResponse:
    """Fetch expert escalation ticket detail by ID."""
    ticket = service.get_escalation_ticket(ticket_id)
    if ticket is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket '{ticket_id}' not found.",
        )
    return ticket


@router.post("/tickets/{ticket_id}/resolve", response_model=EscalationTicketResponse)
async def resolve_escalation_ticket(
    payload: ResolveEscalationTicketRequest,
    ticket_id: str = Path(..., min_length=1, max_length=64, description="Escalation ticket ID"),
    service: ZeroDefenseReVerificationService = Depends(get_zero_defense_reverification_service),
) -> EscalationTicketResponse:
    """Submit expert verdict and resolve an escalation ticket."""
    try:
        return service.resolve_escalation_ticket(ticket_id, payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
