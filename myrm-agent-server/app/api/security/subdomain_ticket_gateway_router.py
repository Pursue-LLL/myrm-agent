"""
[POS] app/api/security/subdomain_ticket_gateway_router.py
[INPUT] fastapi, app.schemas.subdomain_ticket_gateway, app.services.security.subdomain_ticket_gateway_service
[OUTPUT] router

FastAPI router for Short-Lived Ticket Session Exchange & Subdomain Isolated Gateway.
Exposes endpoints for master portal single-use ticket issuance, subdomain ticket redemption,
isolated session token validation, and airgap boundary checking.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.subdomain_ticket_gateway import (
    AirgapEvaluationResponse,
    EvaluateAirgapRequest,
    IssueTicketRequest,
    IssueTicketResponse,
    RedeemTicketRequest,
    RedeemTicketResponse,
    RevokeSessionRequest,
    RevokeSessionResponse,
    SubdomainGatewayMetricsResponse,
    ValidateSessionRequest,
    ValidateSessionResponse,
)
from app.services.security.subdomain_ticket_gateway_service import (
    SubdomainTicketGatewayService,
    get_subdomain_ticket_gateway_service,
)

router = APIRouter(
    prefix="/subdomain-ticket-gateway",
    tags=["Short-Lived Ticket Session Exchange & Subdomain Isolated Gateway"],
)


@router.post(
    "/tickets/issue",
    response_model=IssueTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Issue a 30s single-use ticket for cross-subdomain handshake",
)
def issue_ticket(
    request: IssueTicketRequest,
    service: SubdomainTicketGatewayService = Depends(get_subdomain_ticket_gateway_service),
) -> IssueTicketResponse:
    """Issue a single-use exchange ticket from master control domain."""
    return service.issue_ticket(request)


@router.post(
    "/tickets/redeem",
    response_model=RedeemTicketResponse,
    status_code=status.HTTP_200_OK,
    summary="Redeem ticket at the subdomain gateway and mint isolated instance session",
)
def redeem_ticket(
    request: RedeemTicketRequest,
    service: SubdomainTicketGatewayService = Depends(get_subdomain_ticket_gateway_service),
) -> RedeemTicketResponse:
    """Validate ticket, check anti-replay/fingerprint constraints, and mint isolated session."""
    return service.redeem_ticket(request)


@router.post(
    "/sessions/validate",
    response_model=ValidateSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate active subdomain instance session token",
)
def validate_session(
    request: ValidateSessionRequest,
    service: SubdomainTicketGatewayService = Depends(get_subdomain_ticket_gateway_service),
) -> ValidateSessionResponse:
    """Verify if session is valid, unexpired, and strictly scoped to instance."""
    return service.validate_session(request)


@router.post(
    "/sessions/revoke",
    response_model=RevokeSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Revoke an active instance session token",
)
def revoke_session(
    request: RevokeSessionRequest,
    service: SubdomainTicketGatewayService = Depends(get_subdomain_ticket_gateway_service),
) -> RevokeSessionResponse:
    """Revoke instance session token upon logout or suspicion."""
    return service.revoke_session(request)


@router.post(
    "/airgap/evaluate",
    response_model=AirgapEvaluationResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect destination endpoint against subdomain airgap rules",
)
def evaluate_airgap(
    request: EvaluateAirgapRequest,
    service: SubdomainTicketGatewayService = Depends(get_subdomain_ticket_gateway_service),
) -> AirgapEvaluationResponse:
    """Inspect outbound API destination from sandbox against least-privilege airgap constraints."""
    return service.evaluate_airgap(request)


@router.get(
    "/metrics",
    response_model=SubdomainGatewayMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Retrieve cumulative metrics for tickets, replays, and airgap enforcement",
)
def get_metrics(
    service: SubdomainTicketGatewayService = Depends(get_subdomain_ticket_gateway_service),
) -> SubdomainGatewayMetricsResponse:
    """Get metrics tracking tickets, replay attempts, airgap violations, and active sessions."""
    return service.get_metrics()
