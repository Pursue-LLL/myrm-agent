"""Pydantic DTO schemas for Desktop OAuth Browser Flow & RFC 8628 Device Code Grant.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for PKCE desktop login initialization, device code sessions,
  device authorization polling, and silent token rotation.

[POS]
- Server schemas. Exposes typed contracts for browser-based and headless zero-key authorization.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class DesktopOAuthInitRequest(BaseModel):
    """Request payload to initiate PKCE desktop browser OAuth flow."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., description="Target OAuth provider: github, google, anthropic, openai, custom")
    client_id: str = Field(..., description="OAuth client ID")
    base_auth_url: str = Field(..., description="OAuth provider authorize endpoint URL")
    scopes: list[str] = Field(default_factory=list, description="Requested OAuth scopes")
    loopback_port: int = Field(default=41920, description="Local loopback redirect port")


class DesktopOAuthInitResponseDto(BaseModel):
    """Response payload containing PKCE authorization URL and verifier for local loopback exchange."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., description="OAuth provider")
    authorization_url: str = Field(..., description="Full URL to open in user's default browser")
    state: str = Field(..., description="Cryptographic CSRF state token")
    code_verifier: str = Field(..., description="PKCE code verifier to retain in memory for callback")
    redirect_uri: str = Field(..., description="Local loopback redirect URI")


class DeviceCodeInitRequest(BaseModel):
    """Request payload to initiate RFC 8628 device authorization flow."""

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(..., description="Client identifier")
    verification_uri: str = Field(..., description="Base URL where the user enters the verification code")
    scope: str = Field(default="", description="Requested scopes")
    expires_in: int = Field(default=600, description="User code validity duration in seconds")
    interval: int = Field(default=5, description="Recommended polling interval in seconds")


class DeviceCodeSessionDto(BaseModel):
    """Active RFC 8628 device code session specification."""

    model_config = ConfigDict(extra="forbid")

    device_code: str = Field(..., description="High-entropy device code used for background polling")
    user_code: str = Field(..., description="8-character user code (XXXX-XXXX) to display in CLI/sandbox")
    verification_uri: str = Field(..., description="Verification URL to visit")
    verification_uri_complete: str = Field(..., description="Verification URL pre-filled with user_code")
    expires_in: int = Field(..., description="Session lifetime in seconds")
    interval: int = Field(..., description="Polling interval in seconds")
    status: str = Field(..., description="Current authorization status")


class DeviceCodeAuthorizeRequest(BaseModel):
    """Request payload to simulate or submit human approval of a user code."""

    model_config = ConfigDict(extra="forbid")

    user_code: str = Field(..., description="8-character user code shown on device")
    access_token: str = Field(..., description="Access token granted upon approval")
    refresh_token: str | None = Field(default=None, description="Optional refresh token")
    expires_in: int = Field(default=3600, description="Token validity lifetime in seconds")


class DeviceCodePollRequest(BaseModel):
    """Request payload to poll device code authorization status."""

    model_config = ConfigDict(extra="forbid")

    device_code: str = Field(..., description="Device code returned during initiation")
    enforce_interval: bool = Field(default=False, description="Enforce minimum polling interval")


class DeviceCodePollResponseDto(BaseModel):
    """Outcome of device authorization polling."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(..., description="authorization_pending, authorized, slow_down, access_denied, or expired_token")
    access_token: str | None = Field(default=None, description="Access token if authorized")
    refresh_token: str | None = Field(default=None, description="Refresh token if authorized")
    message: str = Field(default="", description="Human-readable status description")


class TokenRotationRequest(BaseModel):
    """Request payload to check and perform silent token rotation."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., description="Provider name")
    buffer_seconds: float = Field(default=60.0, description="Expiration buffer threshold in seconds")
    simulate_new_access_token: str | None = Field(
        default=None, description="Simulate new rotated access token value for testing"
    )


class TokenRotationResponseDto(BaseModel):
    """Outcome of token validity inspection and silent renewal."""

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(..., description="Provider name")
    status: str = Field(..., description="ACTIVE, EXPIRING_SOON, EXPIRED, or REVOKED")
    rotated: bool = Field(..., description="Whether a silent rotation was performed")
    access_token: str | None = Field(default=None, description="Active or newly rotated access token")
    message: str = Field(default="", description="Result detail description")
