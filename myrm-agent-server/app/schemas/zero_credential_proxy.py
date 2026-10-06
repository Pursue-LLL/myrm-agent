"""Pydantic schemas for Enterprise Zero-Credential Proxy and Super-CLI Suite.

[INPUT]
- pydantic::{BaseModel, Field}
- enum::{StrEnum}

[OUTPUT]
- AuthHeaderSchemeEnum: authentication header schemes.
- RegisterProxyRuleRequest, ProxyRuleMetadataResponse: proxy rule registration schemas.
- OutboundProxyRelayRequest, OutboundProxyRelayResponse: relay forwarding schemas.
- SanitizeTextRequest, SanitizeTextResponse: text sanitization schemas.
- SuperCliExecuteRequest, SuperCliExecuteResponse: super CLI invocation schemas.

[POS]
app/schemas/zero_credential_proxy defines API schemas for zero-credential proxy and secure CLI.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class AuthHeaderSchemeEnum(StrEnum):
    """Authentication header schemes."""

    BEARER = "bearer"
    BASIC = "basic"
    CUSTOM = "custom"


class RegisterProxyRuleRequest(BaseModel):
    """Request payload to register an outbound proxy credential injection rule."""

    rule_id: str = Field(..., description="Unique rule/connector identifier")
    target_domain: str = Field(..., description="Target service domain allowlist")
    real_token: str = Field(..., min_length=1, description="Actual sensitive token/key")
    header_name: str = Field(default="Authorization", description="Target header name")
    scheme: AuthHeaderSchemeEnum = Field(
        default=AuthHeaderSchemeEnum.BEARER, description="Auth scheme"
    )
    custom_header_prefix: str = Field(
        default="", description="Optional custom prefix for header value"
    )
    description: str = Field(default="", description="Rule description")


class ProxyRuleMetadataResponse(BaseModel):
    """Response containing proxy injection rule with redacted secret."""

    rule_id: str
    target_domain: str
    real_token: str = Field(default="[REDACTED_IN_VAULT]")
    header_name: str
    scheme: AuthHeaderSchemeEnum
    custom_header_prefix: str
    description: str


class OutboundProxyRelayRequest(BaseModel):
    """Request payload sent from sandbox to be proxied with credentials."""

    url: str = Field(..., description="Target URL")
    method: str = Field(default="GET", description="HTTP method")
    headers: dict[str, str] = Field(default_factory=dict, description="Request headers")
    body: str = Field(default="", description="Request body")
    connector_ref: str | None = Field(
        default=None, description="Optional connector reference ID"
    )


class OutboundProxyRelayResponse(BaseModel):
    """Response returned from outbound proxy gateway."""

    status_code: int
    headers: dict[str, str]
    body: str
    credential_injected: bool
    matched_rule_id: str | None
    redacted_count: int
    transparency_notice: str | None
    blocked_reason: str | None


class SanitizeTextRequest(BaseModel):
    """Request payload to sanitize sensitive tokens from text."""

    text: str = Field(..., description="Raw output or stacktrace text")
    inject_notice: bool = Field(
        default=True, description="Whether to append model transparency notice"
    )


class SanitizeTextResponse(BaseModel):
    """Outcome of redaction gate sanitization."""

    sanitized_text: str
    redacted_count: int
    transparency_notice: str | None
    matched_patterns: list[str]


class SuperCliExecuteRequest(BaseModel):
    """Request payload to execute a command through Super-CLI wrapper."""

    target_cli: str = Field(..., description="Target executable name (e.g. kubectl, gh, aws)")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    injected_env: dict[str, str] = Field(
        default_factory=dict, description="Transient memory-only environment variables"
    )
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0, description="Execution timeout")


class SuperCliExecuteResponse(BaseModel):
    """Execution result returned from Super-CLI wrapper."""

    exit_code: int
    stdout: str
    stderr: str
    redacted_count: int
    transparency_notice: str | None
