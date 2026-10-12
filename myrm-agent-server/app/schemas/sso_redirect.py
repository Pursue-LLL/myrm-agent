"""Pydantic schemas for SSO Redirect Idempotency and Probe Hysteresis.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for URL validation, idempotent redirect construction,
  and health probe hysteresis evaluations.

[POS]
- Server schemas for IHUI-AI #2728e745 idempotent redirect and probe hysteresis.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class UrlPathCategoryDto(StrEnum):
    """Categorization of a redirect target URL."""

    SAFE_RELATIVE = "safe_relative"
    UNSAFE_RELATIVE = "unsafe_relative"
    ABSOLUTE = "absolute"
    DEEP_LINK = "deep_link"
    INVALID = "invalid"


class ValidateRedirectTargetRequest(BaseModel):
    """Request payload for validating redirect target URLs."""

    model_config = ConfigDict(extra="forbid")

    target_url: str = Field(..., description="Target redirect path or absolute URL")
    allowed_absolute_hosts: list[str] | None = Field(
        default=None, description="Optional whitelist of allowed external hostnames"
    )


class ValidateRedirectTargetResponse(BaseModel):
    """Response payload for redirect target validation."""

    model_config = ConfigDict(extra="forbid")

    target_url: str = Field(..., description="Target URL evaluated")
    is_safe: bool = Field(
        ...,
        description="Whether the redirect target is safe from open redirect attacks",
    )
    category: UrlPathCategoryDto = Field(..., description="URL structural category")
    reason: str | None = Field(
        default=None, description="Explanation when URL is rejected"
    )


class BuildSsoRedirectUrlRequest(BaseModel):
    """Request payload for building an idempotent SSO redirect URL."""

    model_config = ConfigDict(extra="forbid")

    redirect_uri: str = Field(
        ..., description="Base redirect URL which may already contain sso_code"
    )
    sso_code: str = Field(..., description="Fresh authorization code to attach")
    code_param: str = Field(
        default="sso_code", description="Query parameter name for authorization code"
    )


class BuildSsoRedirectUrlResponse(BaseModel):
    """Response payload containing the rewritten idempotent redirect URL."""

    model_config = ConfigDict(extra="forbid")

    original_url: str = Field(..., description="Input redirect URI")
    cleaned_url: str = Field(..., description="URL with previous code stripped")
    final_url: str = Field(
        ..., description="Rewritten URL with only the fresh authorization code attached"
    )
    code_attached: str = Field(..., description="Authorization code attached")
    is_relative: bool = Field(
        ..., description="Whether the output preserves relative path format"
    )


class EvaluateProbeRequest(BaseModel):
    """Request payload for recording a connection probe and updating hysteresis."""

    model_config = ConfigDict(extra="forbid")

    is_success: bool = Field(
        ..., description="Outcome of the latest connection or health probe"
    )


class EvaluateProbeResponse(BaseModel):
    """Response payload containing hysteresis evaluation results."""

    model_config = ConfigDict(extra="forbid")

    previous_state: str = Field(
        ..., description="Previous hysteresis state (online, degraded, offline)"
    )
    new_state: str = Field(
        ..., description="Current hysteresis state after probe outcome"
    )
    consecutive_failures: int = Field(
        ..., description="Current tally of consecutive failed probes"
    )
    consecutive_successes: int = Field(
        ..., description="Current tally of consecutive successful probes"
    )
    state_changed: bool = Field(
        ..., description="Whether this probe caused a state transition"
    )
    recommended_action: str = Field(
        ...,
        description="Action recommendation (e.g. observe, switch_to_offline_fallback)",
    )
