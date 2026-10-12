"""
[POS] app/schemas/case_variant_scrubber.py
[INPUT] pydantic, enum
[OUTPUT] ScrubActionEnumResponse, OAuthPKCEChallengeMethodEnum, ScrubbedEnvRecordResponse, ScrubEnvironmentRequest, ScrubEnvironmentResponse, DetectInjectionsRequest, DetectInjectionsResponse, InitiatePKCEFlowRequest, InitiatePKCEFlowResponse, ExchangePKCETokenRequest, ExchangePKCETokenResponse, OAuthProviderManifestResponse, RegisterOAuthProviderRequest, RegisterOAuthProviderResponse, ScrubberSuiteMetricsResponse

Pydantic schemas for Case-Variant Credential Scrubbing & Declarative OAuth PKCE Provider Seam Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class ScrubActionEnumResponse(StrEnum):
    """Action applied to sensitive environment variables."""

    DROP = "DROP"
    REDACT_PLACEHOLDER = "REDACT_PLACEHOLDER"
    ALLOW_PASSTHROUGH = "ALLOW_PASSTHROUGH"


class OAuthPKCEChallengeMethodEnum(StrEnum):
    """PKCE challenge derivation method."""

    S256 = "S256"
    PLAIN = "plain"


class ScrubbedEnvRecordResponse(BaseModel):
    """Descriptor of a scrubbed environment entry."""

    original_key: str = Field(..., description="Original raw variable key name")
    folded_key: str = Field(..., description="Normalized case-folded key name")
    action: ScrubActionEnumResponse = Field(..., description="Action taken")
    matched_pattern: str = Field(..., description="Rule pattern matched")
    redacted_value: str = Field(..., description="Sanitized or empty value")


class ScrubEnvironmentRequest(BaseModel):
    """Payload to scrub an environment dictionary."""

    env_dict: dict[str, str] = Field(..., description="Key-value environment dictionary")
    action: ScrubActionEnumResponse = Field(
        default=ScrubActionEnumResponse.DROP,
        description="Scrub action (DROP or REDACT_PLACEHOLDER)",
    )
    whitelist: list[str] | None = Field(
        default=None,
        description="Optional list of whitelisted keys to preserve",
    )


class ScrubEnvironmentResponse(BaseModel):
    """Sanitized environment output and audit report."""

    clean_env: dict[str, str] = Field(..., description="Cleaned environment dictionary")
    total_scanned: int = Field(..., ge=0, description="Total keys scanned")
    total_dropped: int = Field(..., ge=0, description="Keys physically dropped")
    total_redacted: int = Field(..., ge=0, description="Keys masked with placeholder")
    scrubbed_records: list[ScrubbedEnvRecordResponse] = Field(
        ..., description="List of intercepted variable records"
    )
    detected_injections: list[str] = Field(
        ..., description="Detected case-variant injection attempts"
    )
    timestamp: float = Field(..., description="Audit timestamp")


class DetectInjectionsRequest(BaseModel):
    """Payload to probe environment dictionary for suspicious variant injections."""

    env_dict: dict[str, str] = Field(..., description="Key-value environment dictionary")


class DetectInjectionsResponse(BaseModel):
    """Detected suspicious variant keys."""

    suspicious_keys: list[str] = Field(
        ..., description="List of suspicious case-variant keys detected"
    )
    has_injection_risk: bool = Field(..., description="True if any suspicious keys found")


class InitiatePKCEFlowRequest(BaseModel):
    """Payload to initiate OAuth 2.0 PKCE flow."""

    provider_id: str = Field(..., min_length=1, description="Registered provider ID")
    redirect_uri: str = Field(..., min_length=1, description="Browser callback redirect URI")
    ttl_seconds: float = Field(default=600.0, ge=30.0, description="Flow expiration in seconds")


class InitiatePKCEFlowResponse(BaseModel):
    """In-flight PKCE session descriptor and browser redirect URL."""

    flow_id: str = Field(..., description="Session flow identifier")
    provider_id: str = Field(..., description="Provider identifier")
    state_token: str = Field(..., description="Anti-CSRF state token")
    code_challenge: str = Field(..., description="Computed code challenge")
    challenge_method: OAuthPKCEChallengeMethodEnum = Field(..., description="Challenge method")
    authorization_url: str = Field(..., description="Full URL to open in browser")
    expires_at: float = Field(..., description="Epoch expiry timestamp")


class ExchangePKCETokenRequest(BaseModel):
    """Payload to exchange authorization code for token parameters."""

    flow_id: str = Field(..., min_length=1, description="Session flow ID")
    code: str = Field(..., min_length=1, description="Authorization code from redirect")
    state: str = Field(..., min_length=1, description="State token returned from redirect")


class ExchangePKCETokenResponse(BaseModel):
    """Validated parameters ready for upstream token endpoint exchange."""

    token_endpoint: str = Field(..., description="Target token endpoint URL")
    client_id: str = Field(..., description="Client ID")
    grant_type: str = Field(..., description="Grant type (authorization_code)")
    code: str = Field(..., description="Authorization code")
    code_verifier: str = Field(..., description="PKCE code verifier")
    provider_id: str = Field(..., description="Provider identifier")


class OAuthProviderManifestResponse(BaseModel):
    """Registered OAuth provider manifest."""

    provider_id: str = Field(..., description="Unique provider ID")
    display_name: str = Field(..., description="Display label")
    authorization_endpoint: str = Field(..., description="Auth endpoint")
    token_endpoint: str = Field(..., description="Token endpoint")
    client_id: str = Field(..., description="Client ID")
    scopes: list[str] = Field(..., description="Required OAuth scopes")
    challenge_method: OAuthPKCEChallengeMethodEnum = Field(..., description="Challenge method")


class RegisterOAuthProviderRequest(BaseModel):
    """Payload to register third-party model provider OAuth manifest."""

    provider_id: str = Field(..., min_length=1, description="Unique provider ID")
    display_name: str = Field(..., min_length=1, description="Display label")
    authorization_endpoint: str = Field(..., min_length=1, description="Auth endpoint")
    token_endpoint: str = Field(..., min_length=1, description="Token endpoint")
    client_id: str = Field(..., min_length=1, description="Client ID")
    scopes: list[str] = Field(..., description="Required OAuth scopes")
    challenge_method: OAuthPKCEChallengeMethodEnum = Field(
        default=OAuthPKCEChallengeMethodEnum.S256,
        description="Challenge method",
    )


class RegisterOAuthProviderResponse(BaseModel):
    """Confirmation of registered provider."""

    provider: OAuthProviderManifestResponse = Field(..., description="Registered manifest")
    message: str = Field(..., description="Confirmation message")


class ScrubberSuiteMetricsResponse(BaseModel):
    """Cumulative operational metrics."""

    envs_scrubbed_total: int = Field(..., ge=0)
    credentials_intercepted_total: int = Field(..., ge=0)
    injections_detected_total: int = Field(..., ge=0)
    pkce_flows_initiated_total: int = Field(..., ge=0)
    pkce_tokens_exchanged_total: int = Field(..., ge=0)
