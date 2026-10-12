"""
[POS] app/services/security/subdomain_ticket_gateway_service.py
[INPUT] app.schemas.subdomain_ticket_gateway, myrm_agent_harness.core.security.subdomain_ticket_gateway
[OUTPUT] SubdomainTicketGatewayService, get_subdomain_ticket_gateway_service

Service layer for Short-Lived Ticket Session Exchange & Subdomain Isolated Gateway.
Manages anti-replay ticket issuance, subdomain session validation and revocation,
and least-privilege airgap policy evaluation.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.subdomain_ticket_gateway import (
    AirgapEvaluationResult,
    InstanceSessionContext,
    OneTimeExchangeTicket,
    SubdomainIsolatedGatewaySuite,
)

from app.schemas.subdomain_ticket_gateway import (
    AirgapEvaluationResponse,
    EvaluateAirgapRequest,
    InstanceSessionContextResponse,
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

logger = logging.getLogger(__name__)


class SubdomainTicketGatewayService:
    """Service managing ticket exchanges and subdomain airgap enforcement."""

    def __init__(self, suite: SubdomainIsolatedGatewaySuite | None = None) -> None:
        self._suite = suite or SubdomainIsolatedGatewaySuite()

    def issue_ticket(self, request: IssueTicketRequest) -> IssueTicketResponse:
        """Issue a short-lived single-use ticket bound to client IP and fingerprint."""
        ticket: OneTimeExchangeTicket = self._suite.issue_exchange_ticket(
            master_user_id=request.master_user_id,
            target_instance_id=request.target_instance_id,
            client_ip=request.client_ip,
            client_fingerprint=request.client_fingerprint,
        )
        return IssueTicketResponse(
            ticket_id=ticket.ticket_id,
            target_instance_id=ticket.target_instance_id,
            expires_at=ticket.expires_at,
            signature=ticket.signature,
        )

    def redeem_ticket(self, request: RedeemTicketRequest) -> RedeemTicketResponse:
        """Redeem ticket at subdomain gateway and mint isolated instance session."""
        status, session = self._suite.redeem_exchange_ticket(
            ticket_id=request.ticket_id,
            client_ip=request.client_ip,
            client_fingerprint=request.client_fingerprint,
        )

        session_resp: InstanceSessionContextResponse | None = None
        if session is not None:
            session_resp = self._map_session(session)

        return RedeemTicketResponse(
            status=status.value,
            session=session_resp,
        )

    def validate_session(self, request: ValidateSessionRequest) -> ValidateSessionResponse:
        """Validate if an instance session token is valid and scoped to the target instance."""
        is_valid = self._suite.validate_instance_session(
            session_id=request.session_id,
            instance_id=request.instance_id,
        )
        return ValidateSessionResponse(
            session_id=request.session_id,
            instance_id=request.instance_id,
            is_valid=is_valid,
        )

    def revoke_session(self, request: RevokeSessionRequest) -> RevokeSessionResponse:
        """Revoke an active instance session token."""
        success = self._suite.revoke_session(request.session_id)
        return RevokeSessionResponse(
            session_id=request.session_id,
            success=success,
        )

    def evaluate_airgap(self, request: EvaluateAirgapRequest) -> AirgapEvaluationResponse:
        """Inspect destination endpoint against subdomain airgap rules."""
        result: AirgapEvaluationResult = self._suite.evaluate_airgap_request(
            current_instance_id=request.current_instance_id,
            requested_path=request.requested_path,
            target_instance_id=request.target_instance_id,
        )
        return AirgapEvaluationResponse(
            is_allowed=result.is_allowed,
            verdict=result.verdict.value,
            requested_path=result.requested_path,
            target_instance_id=result.target_instance_id,
            diagnostic_reason=result.diagnostic_reason,
        )

    def get_metrics(self) -> SubdomainGatewayMetricsResponse:
        """Retrieve cumulative metrics for tickets, replays, and airgap enforcement."""
        m = self._suite.metrics
        return SubdomainGatewayMetricsResponse(
            tickets_issued_total=m.tickets_issued_total,
            tickets_redeemed_total=m.tickets_redeemed_total,
            replay_attacks_blocked_total=m.replay_attacks_blocked_total,
            airgap_violations_blocked_total=m.airgap_violations_blocked_total,
            active_sessions_total=m.active_sessions_total,
        )

    @staticmethod
    def _map_session(session: InstanceSessionContext) -> InstanceSessionContextResponse:
        return InstanceSessionContextResponse(
            session_id=session.session_id,
            instance_id=session.instance_id,
            user_id=session.user_id,
            issued_at=session.issued_at,
            expires_at=session.expires_at,
            is_revoked=session.is_revoked,
        )


_service_instance: SubdomainTicketGatewayService | None = None


def get_subdomain_ticket_gateway_service() -> SubdomainTicketGatewayService:
    """Dependency provider for SubdomainTicketGatewayService singleton."""
    global _service_instance
    if _service_instance is None:
        _service_instance = SubdomainTicketGatewayService()
    return _service_instance
