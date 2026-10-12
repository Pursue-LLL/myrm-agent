"""
[POS] app/schemas/subdomain_ticket_gateway.py
[INPUT] pydantic
[OUTPUT] IssueTicketRequest, IssueTicketResponse, RedeemTicketRequest, InstanceSessionContextResponse, RedeemTicketResponse, ValidateSessionRequest, ValidateSessionResponse, RevokeSessionRequest, RevokeSessionResponse, EvaluateAirgapRequest, AirgapEvaluationResponse, SubdomainGatewayMetricsResponse

Pydantic schemas for Short-Lived Ticket Session Exchange & Subdomain Isolated Gateway.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IssueTicketRequest(BaseModel):
    """Payload to issue a 30s single-use ticket for cross-subdomain handshake."""

    master_user_id: str = Field(..., description="Authenticated user ID in master portal")
    target_instance_id: str = Field(..., description="Target sandbox instance ID")
    client_ip: str = Field(..., description="Client IP address for anti-spoofing binding")
    client_fingerprint: str = Field(..., description="Client hardware/browser fingerprint digest")


class IssueTicketResponse(BaseModel):
    """Response containing minted single-use exchange ticket."""

    ticket_id: str = Field(..., description="Unique ticket ID")
    target_instance_id: str = Field(..., description="Target instance ID")
    expires_at: float = Field(..., description="Ticket expiry timestamp")
    signature: str = Field(..., description="HMAC-SHA256 signature binding attributes")


class RedeemTicketRequest(BaseModel):
    """Payload to redeem ticket at the subdomain gateway."""

    ticket_id: str = Field(..., description="Single-use ticket identifier")
    client_ip: str = Field(..., description="Client IP presenting the ticket")
    client_fingerprint: str = Field(..., description="Client fingerprint presenting the ticket")


class InstanceSessionContextResponse(BaseModel):
    """Details of the minted isolated subdomain session."""

    session_id: str = Field(..., description="Minted session token for instance subdomain")
    instance_id: str = Field(..., description="Bound instance ID")
    user_id: str = Field(..., description="Authenticated user ID")
    issued_at: float = Field(..., description="Session creation timestamp")
    expires_at: float = Field(..., description="Session expiration timestamp")
    is_revoked: bool = Field(..., description="Whether session is revoked")


class RedeemTicketResponse(BaseModel):
    """Result of ticket redemption and session minting."""

    status: str = Field(..., description="Validation status: VALID, EXPIRED, ALREADY_CONSUMED, FINGERPRINT_MISMATCH, INVALID_SIGNATURE")
    session: InstanceSessionContextResponse | None = Field(
        default=None,
        description="Minted isolated session context if valid",
    )


class ValidateSessionRequest(BaseModel):
    """Payload to verify active instance session token."""

    session_id: str = Field(..., description="Instance session ID to check")
    instance_id: str = Field(..., description="Expected instance ID")


class ValidateSessionResponse(BaseModel):
    """Result of instance session validation."""

    session_id: str = Field(..., description="Checked session ID")
    instance_id: str = Field(..., description="Checked instance ID")
    is_valid: bool = Field(..., description="Whether session is active, unrevoked, and unexpired")


class RevokeSessionRequest(BaseModel):
    """Payload to revoke an instance session."""

    session_id: str = Field(..., description="Target session ID to revoke")


class RevokeSessionResponse(BaseModel):
    """Result of session revocation."""

    session_id: str = Field(..., description="Target session ID")
    success: bool = Field(..., description="Whether session was successfully revoked")


class EvaluateAirgapRequest(BaseModel):
    """Payload inspecting an outbound API call against subdomain airgap rules."""

    current_instance_id: str = Field(..., description="Calling sandbox instance ID")
    requested_path: str = Field(..., description="Requested destination HTTP URI path")
    target_instance_id: str | None = Field(default=None, description="Target instance ID if specified")


class AirgapEvaluationResponse(BaseModel):
    """Enforcement decision from subdomain airgap guard."""

    is_allowed: bool = Field(..., description="Whether request is permitted to proceed")
    verdict: str = Field(..., description="Airgap verdict code")
    requested_path: str = Field(..., description="Evaluated destination path")
    target_instance_id: str = Field(..., description="Target instance ID")
    diagnostic_reason: str = Field(..., description="Explanation of airgap decision")


class SubdomainGatewayMetricsResponse(BaseModel):
    """Cumulative metrics tracking ticket exchanges and airgap enforcement."""

    tickets_issued_total: int = Field(..., description="Total tickets issued from master portal")
    tickets_redeemed_total: int = Field(..., description="Total tickets successfully redeemed")
    replay_attacks_blocked_total: int = Field(..., description="Total replay attempts blocked")
    airgap_violations_blocked_total: int = Field(..., description="Total airgap violations intercepted")
    active_sessions_total: int = Field(..., description="Currently active isolated instance sessions")
