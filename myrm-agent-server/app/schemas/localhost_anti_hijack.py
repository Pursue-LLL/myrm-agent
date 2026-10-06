"""Pydantic schemas for localhost anti-DNS-rebinding and origin guard.

[INPUT]
Standard library typing, pydantic BaseModel and Field.

[OUTPUT]
LocalhostSecurityStatusResponse, OriginAuditRecordResponse, SecurityConfigUpdateRequest.

[POS]
Schema definitions for DNS-rebinding protection and localhost origin hijacking audit models.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class SetupTokenExchangeRequest(BaseModel):
    """Request payload for exchanging a startup setup token for a session cookie."""

    token: str = Field(..., description="High-entropy one-time setup token")
    client_identifier: str | None = Field(
        None, description="Optional client binding identifier"
    )


class SetupTokenExchangeResponse(BaseModel):
    """Response returned upon attempting token exchange."""

    success: bool = Field(..., description="Whether the token exchange succeeded")
    session_id: str | None = Field(
        None, description="Session ID created, also set in HttpOnly cookie"
    )
    message: str = Field(..., description="Status explanation or error reason")
    cookie_name: str = Field(
        "myrm_local_session", description="Name of the issued session cookie"
    )


class HostOriginVerifyRequest(BaseModel):
    """Request payload to test Host and Origin header legitimacy."""

    host: str | None = Field(None, description="Incoming Host header")
    origin: str | None = Field(None, description="Incoming Origin header")
    referer: str | None = Field(None, description="Incoming Referer header")
    client_ip: str | None = Field(None, description="Client remote IP address")


class HostOriginVerifyResponse(BaseModel):
    """Validation outcome for host and origin inspection."""

    is_allowed: bool = Field(..., description="Whether the request is allowed")
    status: Literal[
        "allowed",
        "rejected_host",
        "rejected_origin",
        "rejected_referer",
        "invalid_token",
    ] = Field(..., description="Validation outcome status")
    reason: str = Field(..., description="Detailed security rationale")
    host_header: str | None = Field(None, description="Evaluated Host header")
    origin_header: str | None = Field(None, description="Evaluated Origin header")


class AntiHijackPolicyResponse(BaseModel):
    """Current anti-rebinding and origin whitelist policy."""

    allowed_hosts: list[str] = Field(
        ..., description="Whitelisted host names and addresses"
    )
    allowed_origins: list[str] = Field(..., description="Whitelisted origin URLs")
    allow_null_origin: bool = Field(
        ..., description="Whether 'null' origin is permitted"
    )
    enforce_strict_mode: bool = Field(
        ..., description="Whether strict DNS rebinding mode is active"
    )


class GenerateSetupTokenResponse(BaseModel):
    """Response returned when generating a transient setup token for startup."""

    token: str = Field(..., description="Transient high-entropy startup token")
    expires_at: float = Field(..., description="Unix timestamp of token expiration")
    ttl_seconds: int = Field(..., description="Token validity time in seconds")


class RevokeSessionRequest(BaseModel):
    """Request to revoke an existing session."""

    session_id: str = Field(..., description="Session identifier to terminate")


class RevokeSessionResponse(BaseModel):
    """Response for session revocation."""

    success: bool = Field(..., description="Whether session was revoked successfully")
    message: str = Field(..., description="Outcome message")
