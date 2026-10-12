"""Pydantic schemas for Admin Authentication Surface management.

[INPUT]
- Web requests configuring login methods, OAuth connections, and registration switches.

[OUTPUT]
- Serialized authentication surface configurations and anti-lockout validation responses.

[POS]
- Server-side DTO contracts for unified admin authentication surface governance.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class LoginMethodSettingsDto(BaseModel):
    """Settings controlling primary login methods."""

    password_enabled: bool = Field(
        default=True, description="Whether password login is enabled"
    )
    email_code_enabled: bool = Field(
        default=False, description="Whether email verification code login is enabled"
    )
    email_code_auto_registration_enabled: bool = Field(
        default=False,
        description="Whether email code automatically registers new accounts",
    )


class OAuthConnectionDto(BaseModel):
    """Configuration for a third-party OAuth provider."""

    id: str = Field(description="Unique provider connection identifier")
    provider: Literal["github", "google", "feishu", "gitlab", "oidc_generic"] = Field(
        description="Provider type"
    )
    name: str = Field(description="Display name of connection")
    client_id: str = Field(description="OAuth client identifier")
    client_secret: str = Field(description="OAuth client secret (masked on read)")
    authorize_url: str = Field(
        default="", description="OAuth authorization endpoint URL"
    )
    token_url: str = Field(default="", description="OAuth token endpoint URL")
    scopes: list[str] = Field(
        default_factory=list, description="Requested OAuth scopes"
    )
    issuer_url: str | None = Field(
        default=None, description="OpenID Connect issuer URL if applicable"
    )
    enabled: bool = Field(default=True, description="Whether connection is active")
    auto_registration_enabled: bool = Field(
        default=False,
        description="Whether OAuth sign-in automatically provisions new users",
    )


class AdminAuthSurfaceConfigDto(BaseModel):
    """Unified security configuration for system authentication surface."""

    login_methods: LoginMethodSettingsDto = Field(
        default_factory=LoginMethodSettingsDto,
        description="Primary login method settings",
    )
    oauth_connections: list[OAuthConnectionDto] = Field(
        default_factory=list,
        description="List of configured OAuth identity providers",
    )
    allow_public_registration: bool = Field(
        default=False, description="Global public registration switch"
    )
    mfa_enforced: bool = Field(
        default=False, description="Whether multi-factor authentication is mandatory"
    )


class AuthSurfaceValidationResultDto(BaseModel):
    """Result of validating authentication surface security invariants."""

    is_valid: bool = Field(description="True if configuration passes all rules")
    active_login_method_count: int = Field(
        description="Number of currently enabled login methods"
    )
    errors: list[str] = Field(
        default_factory=list, description="Validation blocking errors"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Non-blocking security warnings"
    )


class UpdateAuthSurfaceRequest(BaseModel):
    """Request payload for updating authentication surface configuration."""

    config: AdminAuthSurfaceConfigDto = Field(
        description="Desired authentication surface configuration"
    )
    preserve_masked_secrets: bool = Field(
        default=True,
        description="Whether to preserve existing secrets when masked in payload",
    )


class UpdateAuthSurfaceResponse(BaseModel):
    """Response returned upon updating authentication surface configuration."""

    config: AdminAuthSurfaceConfigDto = Field(
        description="Applied authentication surface configuration"
    )
    validation: AuthSurfaceValidationResultDto = Field(
        description="Validation outcome of the update"
    )
