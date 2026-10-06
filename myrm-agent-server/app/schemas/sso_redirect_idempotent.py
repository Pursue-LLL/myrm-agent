"""Pydantic schemas for SSO Redirect Idempotence and Probe Hysteresis.

[INPUT]
Request and response payloads for SSO redirect construction and hysteresis tracking.

[OUTPUT]
BuildSsoRedirectRequest, BuildSsoRedirectResponse, ProbeStateSnapshot DTO contracts.

[POS]
Schema definitions supporting secure SSO redirect handling and anti-flapping probe hysteresis.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BuildSsoRedirectRequest(BaseModel):
    """Payload to build an idempotent SSO redirect URL."""

    model_config = ConfigDict(extra="forbid")

    redirect_uri: str = Field(..., description="Target redirect URI or path")
    sso_code: str = Field(..., description="Fresh one-time SSO authorization code")
    param_name: str = Field(
        default="sso_code", description="Query parameter name for authorization code"
    )
    allow_deep_link: bool = Field(
        default=False, description="Whether custom scheme deep links are allowed"
    )
    allowed_origins: list[str] | None = Field(
        default=None, description="Optional whitelist of allowed absolute HTTP/HTTPS origins"
    )
    fallback_url: str = Field(
        default="/", description="Fallback relative URL when redirect_uri is unsafe"
    )


class BuildSsoRedirectResponse(BaseModel):
    """Response containing the constructed idempotent SSO redirect URL."""

    model_config = ConfigDict(extra="forbid")

    original_uri: str = Field(..., description="Original input URI")
    redirect_url: str = Field(..., description="Constructed safe idempotent redirect URL")
    stripped_existing_code: bool = Field(
        ..., description="Whether stale authorization code parameters were purged"
    )
    is_relative: bool = Field(..., description="Whether redirect URL is a relative path")
    is_safe_target: bool = Field(
        ..., description="Whether redirect target passed safety validation"
    )


class ValidateNavigationTargetRequest(BaseModel):
    """Payload to validate navigation target safety against open redirect."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="Navigation target URL or relative path")
    allow_deep_link: bool = Field(
        default=False, description="Whether custom scheme deep links are permitted"
    )
    allowed_origins: list[str] | None = Field(
        default=None, description="Optional whitelist of allowed HTTP/HTTPS origins"
    )
    fallback_url: str = Field(
        default="/", description="Fallback URL to return if target is unsafe"
    )


class ValidateNavigationTargetResponse(BaseModel):
    """Validation outcome for navigation target safety."""

    model_config = ConfigDict(extra="forbid")

    target: str = Field(..., description="Original input target")
    is_safe: bool = Field(..., description="Whether target is safe against open redirect")
    is_same_origin_relative: bool = Field(
        ..., description="Whether target is a strictly same-origin relative path"
    )
    resolved_safe_target: str = Field(
        ..., description="Resolved safe navigation destination"
    )


class RecordProbeRequest(BaseModel):
    """Payload to record a network health probe outcome."""

    model_config = ConfigDict(extra="forbid")

    healthy: bool = Field(..., description="Whether network health probe succeeded")
    current_url: str | None = Field(
        default=None, description="Active client view URL when probe occurred"
    )


class RecordProbeResponse(BaseModel):
    """Response reporting hysteresis state and suggested client navigation."""

    model_config = ConfigDict(extra="forbid")

    is_online: bool = Field(
        ..., description="Whether client shell remains in online state"
    )
    transitioned_to_offline: bool = Field(
        ..., description="Whether this probe triggered a transition to offline mode"
    )
    transitioned_to_online: bool = Field(
        ..., description="Whether this probe triggered a recovery to online mode"
    )
    consecutive_fails: int = Field(
        ..., description="Current count of consecutive probe failures"
    )
    last_healthy_url: str | None = Field(
        default=None, description="Last known healthy active URL before disconnection"
    )
    suggested_navigation_url: str = Field(
        ..., description="Recommended client navigation destination URL"
    )
