"""Pydantic schemas for Streaming Endpoint Identity Gate Parity.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for streaming endpoint contracts, client identity assertions,
  gate verdicts, and parity defect audit reports.

[POS]
- Server schemas. Exposes typed contracts for client UI and streaming gateway enforcement.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StreamingEndpointContractDto(BaseModel):
    """Declared security gate contract for a streaming route."""

    model_config = ConfigDict(extra="forbid")

    endpoint_path: str = Field(..., description="Route path of the streaming endpoint")
    transport: str = Field(..., description="Transport protocol: SSE, WEBSOCKET, CHUNKED_STREAM")
    requires_auth: bool = Field(default=True, description="Whether authentication is strictly enforced")
    required_scope: str | None = Field(default=None, description="Required authorization permission scope")
    target_resource_type: str | None = Field(
        default=None, description="Resource classification: chat, task, eval, notification, wiki"
    )
    supports_remote_access: bool = Field(
        default=True, description="Whether endpoint is accessible over remote network"
    )


class StreamingClientIdentityDto(BaseModel):
    """Resolved client identity asserting access to a stream."""

    model_config = ConfigDict(extra="forbid")

    subject_id: str | None = Field(default=None, description="Authenticated user or service subject ID")
    auth_source: str | None = Field(default=None, description="Authentication mechanism: bearer, pair_token, etc.")
    granted_scopes: list[str] = Field(default_factory=list, description="Scopes held by client token")
    bound_resource_ids: list[str] = Field(
        default_factory=list, description="Specific resource IDs this token is confined to"
    )
    is_loopback: bool = Field(default=False, description="Whether connection originates from localhost")
    is_remote: bool = Field(default=False, description="Whether connection is traversing remote network")


class StreamingGateVerdictDto(BaseModel):
    """Outcome of streaming gate evaluation."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(..., description="ALLOWED, DENIED_UNAUTHENTICATED, DENIED_SCOPE_MISMATCH, etc.")
    endpoint_path: str = Field(..., description="Target route evaluated")
    reason: str = Field(..., description="Detailed explanation of the access decision")
    status_code: int = Field(..., description="HTTP status code (200, 401, 403)")


class StreamingParityAuditIssueDto(BaseModel):
    """Parity defect discovered on a streaming route."""

    model_config = ConfigDict(extra="forbid")

    endpoint_path: str = Field(..., description="Offending streaming endpoint path")
    transport: str = Field(..., description="Transport protocol")
    issue_type: str = Field(..., description="Defect category: UNAUTHENTICATED_STREAM, UNSCOPED_RESOURCE_STREAM")
    description: str = Field(..., description="Detailed issue description")
    severity: str = Field(..., description="CRITICAL, HIGH, MEDIUM, LOW")


class EvaluateStreamingAccessRequest(BaseModel):
    """Payload to evaluate access to a streaming endpoint."""

    model_config = ConfigDict(extra="forbid")

    endpoint_path: str = Field(..., description="Target streaming route path")
    client_identity: StreamingClientIdentityDto = Field(..., description="Client identity parameters")
    requested_resource_id: str | None = Field(
        default=None, description="Target resource ID (e.g. chat_id, task_id) requested by client"
    )


class EvaluateStreamingAccessResponse(BaseModel):
    """Evaluation response."""

    model_config = ConfigDict(extra="forbid")

    verdict: StreamingGateVerdictDto = Field(..., description="Gate evaluation outcome")
    allowed: bool = Field(..., description="Boolean convenience flag: True if access is allowed")


class StreamingParityAuditResponse(BaseModel):
    """Summary report of streaming identity gate parity audit."""

    model_config = ConfigDict(extra="forbid")

    total_endpoints_evaluated: int = Field(..., description="Count of streaming endpoints audited")
    total_issues_found: int = Field(..., description="Count of parity security defects detected")
    is_compliant: bool = Field(..., description="True if all endpoints enforce REST-parity authentication")
    issues: list[StreamingParityAuditIssueDto] = Field(
        default_factory=list, description="Detected security parity issues"
    )
