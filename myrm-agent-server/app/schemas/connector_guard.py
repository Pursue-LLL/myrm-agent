"""Pydantic schemas for Connector Host Allowlist and Anti-Exfiltration SSRF Guard API.

[INPUT]
- pydantic::{BaseModel, Field}
- datetime::{datetime}

[OUTPUT]
- InspectTrafficRequest, InspectTrafficResponse: traffic inspection schemas.
- RegisterConnectorRequest, ConnectorEntryResponse: connector allowlist registration schemas.
- SetOutboundModeRequest, ResetCircuitBreakerRequest, CircuitBreakerStatusResponse: circuit breaker schemas.
- ThreatAlertResponse: security alert schema.

[POS]
app/schemas/connector_guard defines API schemas for SSRF guard, connector registry, and circuit breakers.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class InspectTrafficRequest(BaseModel):
    """Request payload for vetting an outbound HTTP request."""

    url: str = Field(..., description="Outbound request target URL")
    method: str = Field(default="GET", description="HTTP request method")
    headers: dict[str, str] = Field(default_factory=dict, description="Outbound request headers")
    query_params: dict[str, str] = Field(default_factory=dict, description="Parsed query parameters")
    connector_id: str | None = Field(default=None, description="Optional target connector ID")
    session_id: str = Field(default="default_session", description="Agent session ID")


class InspectTrafficResponse(BaseModel):
    """Decision and sanitized outbound traffic metadata."""

    decision: str = Field(..., description="Guard enforcement decision")
    reason: str = Field(..., description="Reason for decision")
    detected_threat: str | None = Field(default=None, description="Identified threat kind if any")
    sanitized_headers: dict[str, str] = Field(default_factory=dict, description="Headers sanitized of credentials if needed")
    can_inject_credential: bool = Field(..., description="Whether outbound proxy is permitted to inject credential")
    matched_connector_id: str | None = Field(default=None, description="Matched connector ID if authorized")


class RegisterConnectorRequest(BaseModel):
    """Payload to register an official connector endpoint allowlist."""

    connector_id: str = Field(..., description="Unique connector identifier")
    official_hosts: list[str] = Field(..., min_length=1, description="Authorized official hostnames")
    allow_subdomains: bool = Field(default=False, description="Whether to allow wildcard subdomains")
    allowed_schemes: list[str] = Field(default_factory=lambda: ["https"], description="Allowed URL schemes")
    description: str = Field(default="", description="Human-readable description")


class ConnectorEntryResponse(BaseModel):
    """Registered connector entry details."""

    connector_id: str
    official_hosts: list[str]
    allow_subdomains: bool
    allowed_schemes: list[str]
    description: str


class ThreatAlertResponse(BaseModel):
    """Captured SSRF or token exfiltration security alert."""

    alert_id: str
    session_id: str
    url: str
    threat_kind: str
    description: str
    blocked: bool
    timestamp: datetime


class ResetCircuitBreakerRequest(BaseModel):
    """Request to reset tripped circuit breaker for a session."""

    session_id: str = Field(..., description="Session identifier to reset")


class CircuitBreakerStatusResponse(BaseModel):
    """Current circuit breaker state for a session."""

    session_id: str
    tripped: bool


class SetOutboundModeRequest(BaseModel):
    """Payload to configure enterprise outbound policy mode."""

    mode: str = Field(..., description="Mode: 'strict_block_unregistered' or 'zero_cred_permissive'")
