"""Pydantic schemas for Muse-Style Secure VM Isolation and Sentinel Suite API.

[INPUT]
- Pydantic BaseModel and Field from pydantic.

[OUTPUT]
- DTO schemas for secure VM profiles, ephemeral single-use tokens, and sentinel traffic reviews.

[POS]
Schema layer defining secure VM isolation and sentinel traffic inspection DTOs.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RegisterVmRequest(BaseModel):
    """Payload to register a user-dedicated secure sandbox VM."""

    user_id: str = Field(..., description="Unique user or tenant identifier")
    isolation_tier: str = Field(
        default="dedicated_secure_vm",
        description="Isolation level: 'dedicated_secure_vm', 'container_namespace', 'local_restricted'",
    )
    volume_mount: str | None = Field(
        default=None, description="Path to isolated persistent volume"
    )


class SecureVmProfileResponse(BaseModel):
    """Secure sandbox VM environment descriptor."""

    vm_id: str
    user_id: str
    isolation_tier: str
    volume_mount: str
    egress_mode: str
    credential_sealed: bool
    created_at: datetime


class ReviewOutboundTrafficRequest(BaseModel):
    """Outbound traffic payload submitted to Sentinel for pre-egress screening."""

    request_id: str = Field(..., description="Unique request trace ID")
    destination_url: str = Field(..., description="Destination target URL")
    method: str = Field(default="POST", description="HTTP verb")
    headers: dict[str, str] = Field(
        default_factory=dict, description="Outbound request HTTP headers"
    )
    body_preview: str = Field(default="", description="Serialized payload or preview snippet")
    source_vm_id: str = Field(default="default_vm", description="Source secure VM identifier")


class SentinelReviewResultResponse(BaseModel):
    """Decision produced by Sentinel outbound traffic inspection."""

    request_id: str
    verdict: str = Field(..., description="Verdict: 'allow', 'block', 'require_challenge'")
    matched_rule: str | None
    reason: str
    risk_score: float
    timestamp: datetime


class IssueSingleUseTokenRequest(BaseModel):
    """Payload to mint a short-lived single-use virtual token or payment credential."""

    token_type: str = Field(
        default="virtual_payment_card",
        description="Token category: 'virtual_payment_card', 'ephemeral_bearer_token', 'single_use_api_key'",
    )
    max_amount: float = Field(
        default=100.0, ge=0.01, description="Hard expenditure or credit authorization limit"
    )
    currency: str = Field(default="USD", description="Currency code (e.g. USD, EUR, CNY)")
    bound_recipient: str = Field(
        default="*", description="Bound target merchant or recipient (* for open)"
    )
    ttl_seconds: int = Field(
        default=300, ge=1, le=86400, description="Token validity window in seconds"
    )


class SingleUseTokenResponse(BaseModel):
    """Issued ephemeral single-use credential details."""

    token_id: str
    virtual_token: str
    token_type: str
    max_amount: float
    currency: str
    bound_recipient: str
    is_consumed: bool
    expires_at: datetime
    created_at: datetime


class RedeemSingleUseTokenRequest(BaseModel):
    """Payload to redeem and burn a single-use credential."""

    virtual_token: str = Field(..., description="Virtual token string to redeem")
    amount: float = Field(..., ge=0.01, description="Redemption transaction amount")
    currency: str = Field(default="USD", description="Transaction currency")
    recipient: str = Field(..., description="Claiming recipient or merchant identifier")


class TokenRedemptionResultResponse(BaseModel):
    """Outcome of single-use token redemption attempt."""

    token_id: str
    success: bool
    reason: str
    timestamp: datetime
