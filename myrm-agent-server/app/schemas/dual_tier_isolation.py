"""Pydantic DTO schemas for Dual-Tier Root Admin & User API Key Isolation Suite.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for Root Admin key registration, User API key derivation,
  and dual-tier control-plane/data-plane access evaluation.

[POS]
- Server schemas. Exposes typed contracts for physical control/data plane isolation.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class RegisterAdminKeyRequest(BaseModel):
    """Request payload to register a Root Admin API key for control-plane management."""

    model_config = ConfigDict(extra="forbid")

    allowed_scopes: list[str] = Field(
        default_factory=list, description="Optional administrative scopes"
    )
    custom_raw_key: str | None = Field(
        default=None, description="Optional custom key (e.g. from ov.conf/env)"
    )


class RegisterAdminKeyResponseDto(BaseModel):
    """Specification of registered Root Admin key."""

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(..., description="Unique key identifier")
    raw_key: str = Field(..., description="High-entropy raw admin key (myrm_adm_...)")
    tier: str = Field(..., description="ROOT_ADMIN")
    allowed_scopes: list[str] = Field(default_factory=list, description="Configured scopes")


class DeriveUserKeyRequest(BaseModel):
    """Request payload to derive an isolated User API key bound to a tenant/user context."""

    model_config = ConfigDict(extra="forbid")

    user_id: str = Field(..., description="Target user identifier")
    tenant_id: str | None = Field(
        default=None, description="Enterprise tenant identifier"
    )
    agent_id: str | None = Field(
        default=None, description="Specific agent identifier binding"
    )
    allowed_scopes: list[str] = Field(
        default_factory=list, description="Scoped data permissions"
    )


class DeriveUserKeyResponseDto(BaseModel):
    """Specification of derived User API key."""

    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(..., description="Unique key identifier")
    raw_key: str = Field(..., description="High-entropy raw user key (myrm_usr_...)")
    tier: str = Field(..., description="DERIVED_USER")
    user_id: str = Field(..., description="Owner user ID")
    tenant_id: str = Field(..., description="Bound tenant ID")
    agent_id: str | None = Field(default=None, description="Bound agent ID")
    allowed_scopes: list[str] = Field(default_factory=list, description="Permitted scopes")


class EvaluateAccessRequest(BaseModel):
    """Request payload to evaluate access permission against the dual-tier physical gate."""

    model_config = ConfigDict(extra="forbid")

    raw_key: str = Field(..., description="API key to inspect")
    requested_plane: str = Field(
        ..., description="Target plane: CONTROL_PLANE or DATA_PLANE"
    )
    target_user_id: str | None = Field(
        default=None, description="Target user context for data-plane requests"
    )
    target_tenant_id: str | None = Field(
        default=None, description="Target tenant context for data-plane requests"
    )
    requested_scope: str = Field(
        default="", description="Specific capability or scope requested"
    )


class EvaluateAccessResponseDto(BaseModel):
    """Outcome of access verification through dual-tier physical isolation gate."""

    model_config = ConfigDict(extra="forbid")

    verdict: str = Field(
        ...,
        description="PERMITTED, BLOCKED_DATA_PLANE_VIOLATION, BLOCKED_CONTROL_PLANE_VIOLATION, "
        "BLOCKED_CROSS_TENANT_BREACH, BLOCKED_INVALID_KEY, or BLOCKED_REVOKED_KEY",
    )
    is_permitted: bool = Field(..., description="True if operation is authorized")
    effective_tier: str | None = Field(
        default=None, description="ROOT_ADMIN or DERIVED_USER"
    )
    user_id: str | None = Field(default=None, description="Bound user ID")
    tenant_id: str | None = Field(default=None, description="Bound tenant ID")
    audit_id: str = Field(..., description="Unique immutable audit event identifier")
    message: str = Field(..., description="Evaluation decision trail and explanation")
