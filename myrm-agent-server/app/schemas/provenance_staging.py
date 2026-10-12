"""Pydantic schemas for Session Entity Provenance Gate, Staging Approvals, and Hard Caps.

[INPUT]
None.

[OUTPUT]
DTO models for entity provenance tracking, two-stage change staging, host approval tokens,
and Python hardcoded business caps validation.

[POS]
Server schemas. Exposes typed contracts for Anthropic Commerce Agents-style security gates.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class RegisterSeenEntitiesRequest(BaseModel):
    """Payload to register entity IDs returned by read-only query tools."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session identifier")
    entity_ids: list[str] = Field(..., description="List of observed entity IDs")
    entity_type: str = Field(default="general_entity", description="Domain classification of entities")
    source_tool: str = Field(default="read_query", description="Name of the authenticated read tool")


class RegisterSeenEntitiesResponse(BaseModel):
    """Response acknowledging registered observed entities."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session identifier")
    registered_count: int = Field(..., description="Number of newly registered entities")
    total_observed_count: int = Field(..., description="Total entities observed in this session")


class CheckProvenanceRequest(BaseModel):
    """Payload to check whether an entity ID is verified in the session before write/mutation."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session identifier")
    entity_id: str = Field(..., description="Candidate entity ID to check")
    tool_name: str = Field(default="mutation_tool", description="Name of the impending write tool")


class CheckProvenanceResponse(BaseModel):
    """Provenance check verdict."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session identifier")
    entity_id: str = Field(..., description="Checked entity ID")
    allowed: bool = Field(..., description="True if entity was observed and write is authorized")
    reason: str = Field(..., description="Policy verdict explanation")


class StagedChangeDraftDto(BaseModel):
    """Representation of a staged high-impact mutation draft."""

    model_config = ConfigDict(extra="forbid")

    staged_id: str = Field(..., description="Unique staged change ID")
    session_id: str = Field(..., description="Associated session ID")
    target_entity_id: str = Field(..., description="Target entity ID to mutate")
    mutation_type: str = Field(..., description="Type of mutation (price_change, delete, etc.)")
    diff_payload: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Diff payload")
    status: str = Field(..., description="Lifecycle status (staged, approved, applied, rejected, expired)")
    host_token_id: str | None = Field(default=None, description="Host signed token ID if applied")
    created_at: float = Field(default_factory=time.time, description="Creation timestamp")
    expires_at: float = Field(..., description="Expiration timestamp")


class StageChangeRequest(BaseModel):
    """Payload to propose and hold a high-impact mutation in staging."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session identifier")
    target_entity_id: str = Field(..., description="Target entity ID to mutate")
    mutation_type: str = Field(..., description="Type of mutation")
    diff_payload: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Diff payload")
    ttl_seconds: float = Field(default=300.0, description="Staging draft time-to-live in seconds")


class HostApprovalTokenDto(BaseModel):
    """Host platform signed token model."""

    model_config = ConfigDict(extra="forbid")

    token_id: str = Field(..., description="Unique token identifier")
    staged_id: str = Field(..., description="Associated staged change ID")
    operator_id: str = Field(..., description="Host human operator identity")
    signature: str = Field(..., description="HMAC-SHA256 signature")
    issued_at: float = Field(default_factory=time.time, description="Issuance timestamp")
    valid_until: float = Field(..., description="Expiration timestamp")


class IssueHostTokenRequest(BaseModel):
    """Payload to issue an authentic host signed approval token."""

    model_config = ConfigDict(extra="forbid")

    staged_id: str = Field(..., description="Target staged change ID")
    operator_id: str = Field(..., description="Authorizing host operator identifier")
    ttl_seconds: float = Field(default=60.0, description="Token validity window in seconds")


class ApplyStagedChangeRequest(BaseModel):
    """Payload to apply a staged change presenting host token."""

    model_config = ConfigDict(extra="forbid")

    staged_id: str = Field(..., description="Target staged change ID")
    token: HostApprovalTokenDto = Field(..., description="Authentic host signed token")


class RejectStagedChangeRequest(BaseModel):
    """Payload to reject and cancel a staged mutation draft."""

    model_config = ConfigDict(extra="forbid")

    staged_id: str = Field(..., description="Target staged change ID")


class CapsViolationDto(BaseModel):
    """Details of a breached business limit with compliant alternative."""

    model_config = ConfigDict(extra="forbid")

    parameter_name: str = Field(..., description="Breached parameter name")
    attempted_value: float = Field(..., description="Value proposed by model")
    max_allowed_value: float = Field(..., description="Hard limit cap")
    compliant_alternative: float = Field(..., description="Compliant fallback value")
    message: str = Field(..., description="Diagnostic warning message")


class CheckCapsRequest(BaseModel):
    """Payload to validate numerical parameters against Python hard caps."""

    model_config = ConfigDict(extra="forbid")

    discount_percent: float | None = Field(default=None, description="Promotional discount percentage")
    affected_rows: int | None = Field(default=None, description="Number of database rows to mutate")
    budget_delta: float | None = Field(default=None, description="Financial spend increment")


class CheckCapsResponse(BaseModel):
    """Verdict on business caps check."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(..., description="True if all parameters comply with hard caps")
    violations: list[CapsViolationDto] = Field(default_factory=list, description="List of breaches")
