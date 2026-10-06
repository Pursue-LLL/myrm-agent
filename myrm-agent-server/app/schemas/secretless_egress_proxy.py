"""Pydantic schemas for Secretless Credential Egress Proxy and Placeholder Swap Suite.

[INPUT]
- None (Self-contained Pydantic schemas)

[OUTPUT]
- BoundCredentialRegisterRequest, BoundCredentialResponse, BoundCredentialRevokeRequest
- InspectSwapRequest, InspectSwapResponse, SwapEventResponse

[POS]
Schema definitions for domain-bound credentials and placeholder swap egress audit.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BoundCredentialRegisterRequest(BaseModel):
    """Request payload to register a domain-bound credential."""

    target_host: str = Field(..., description="Target domain host, e.g. 'api.github.com'")
    real_secret: str = Field(..., description="Sensitive secret value held strictly outside sandbox")
    auth_header_name: str = Field(
        default="Authorization",
        description="HTTP header name for injecting credentials",
    )
    auth_header_template: str = Field(
        default="Bearer {secret}",
        description="Header value formatting template",
    )


class BoundCredentialRevokeRequest(BaseModel):
    """Request payload to revoke a bound credential."""

    target_host: str = Field(..., description="Target domain host to revoke")


class BoundCredentialResponse(BaseModel):
    """Metadata response for a domain-bound credential (real secret masked)."""

    target_host: str = Field(..., description="Target domain host")
    auth_header_name: str = Field(..., description="Header name")
    auth_header_template: str = Field(..., description="Header template")
    placeholder: str = Field(..., description="Random non-sensitive placeholder exposed to sandbox")
    is_active: bool = Field(..., description="Whether credential binding is active")


class RevokeCredentialResponse(BaseModel):
    """Response returned upon credential revocation."""

    success: bool = Field(..., description="Whether revocation succeeded")
    target_host: str = Field(..., description="Target host revoked")


class InspectSwapRequest(BaseModel):
    """Request payload for egress proxy inspection and credential swap."""

    target_host: str = Field(..., description="Target domain host")
    path: str = Field(default="/", description="Target URL path")
    method: str = Field(default="GET", description="HTTP request method")
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Sandbox outbound HTTP request headers",
    )


class SwapEventResponse(BaseModel):
    """Audit log entry representing proxy inspection and swap result."""

    timestamp: float = Field(..., description="UNIX epoch timestamp")
    target_host: str = Field(..., description="Target domain host")
    path: str = Field(..., description="Request path")
    method: str = Field(..., description="HTTP method")
    placeholder_used: str | None = Field(default=None, description="Placeholder token if present")
    is_swapped: bool = Field(..., description="Whether credential was swapped and injected")
    is_blocked: bool = Field(..., description="Whether egress request was rejected")
    block_reason: str | None = Field(default=None, description="Reason for blocking if applicable")


class InspectSwapResponse(BaseModel):
    """Outcome returned by egress proxy inspection."""

    is_allowed: bool = Field(..., description="Whether outbound request is permitted")
    status_code: int = Field(..., description="HTTP status code (200 on success, 403 on block)")
    headers_to_inject: dict[str, str] = Field(
        default_factory=dict,
        description="Injected authorization headers containing real secret",
    )
    reason: str = Field(default="", description="Explanation or status note")
    event: SwapEventResponse | None = Field(
        default=None,
        description="Associated egress audit log entry",
    )
