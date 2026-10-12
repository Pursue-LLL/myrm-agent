"""
[POS] app/schemas/scoped_approval_gate.py
[INPUT] pydantic
[OUTPUT] Scoped approval grants and risk-tiered gate DTOs
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class IssueGrantRequestDTO(BaseModel):
    """Payload to issue a new scoped approval grant lease."""

    tool_name: str = Field(..., description="Target tool or action being authorized")
    scope: str = Field(
        ...,
        description="Validity scope: once, task, session, 24h, always",
    )
    agent_id: str = Field(..., description="Agent authorized to invoke tool")
    session_id: str = Field(..., description="Conversational session identifier")
    task_id: str | None = Field(default=None, description="Bound task identifier for task-scope leases")
    ttl_seconds: float | None = Field(default=None, description="Custom TTL in seconds")


class ApprovalGrantLeaseDTO(BaseModel):
    """Active or persisted scoped approval voucher."""

    grant_id: str = Field(..., description="Unique grant identifier")
    tool_name: str = Field(..., description="Authorized tool name")
    scope: str = Field(..., description="Grant scope tier")
    agent_id: str = Field(..., description="Authorized agent")
    session_id: str = Field(..., description="Authorized session")
    task_id: str | None = Field(default=None, description="Bound task identifier")
    granted_at: float = Field(..., description="Issuance timestamp")
    expires_at: float | None = Field(default=None, description="Expiration timestamp")
    revoked: bool = Field(..., description="Revocation status")
    use_count: int = Field(..., description="Number of times redeemed")


class RiskEvaluationRequestDTO(BaseModel):
    """Execution context to evaluate against risk tiers and active grants."""

    tool_name: str = Field(..., description="Tool or action to execute")
    risk_tier: str = Field(
        ...,
        description="Risk tier: read_only, low_risk_write, high_risk_write, irreversible_egress",
    )
    agent_id: str = Field(..., description="Agent attempting execution")
    session_id: str = Field(..., description="Session attempting execution")
    task_id: str | None = Field(default=None, description="Task context if running under a task")
    parameters_summary: str = Field(default="", description="Sanitized summary of execution parameters")


class RiskEvaluationResultDTO(BaseModel):
    """Resolution of tiered gate evaluation."""

    decision: str = Field(..., description="Decision resolution: allow, ask, deny")
    reason: str = Field(..., description="Explanation for gate resolution")
    matched_grant_id: str | None = Field(default=None, description="Grant ID matched if redeemed")
    risk_tier: str = Field(..., description="Evaluated risk tier")
    requires_hitl_prompt: bool = Field(..., description="Whether user approval popup is required")


class RevokeGrantResponseDTO(BaseModel):
    """Outcome of revoking an individual lease."""

    success: bool = Field(..., description="Whether grant was successfully revoked")
    grant_id: str = Field(..., description="Grant ID targeted")


class RevokeAllRequestDTO(BaseModel):
    """Payload to bulk-revoke approval leases."""

    agent_id: str | None = Field(default=None, description="Optional agent filter")
    session_id: str | None = Field(default=None, description="Optional session filter")


class RevokeAllResponseDTO(BaseModel):
    """Outcome of bulk revocation."""

    revoked_count: int = Field(..., description="Number of leases revoked")


class ListActiveGrantsResponseDTO(BaseModel):
    """Active leases currently valid."""

    grants: list[ApprovalGrantLeaseDTO] = Field(..., description="Active leases")


class GrantUsageRecordDTO(BaseModel):
    """Historical audit trail entry."""

    record_id: str = Field(..., description="Unique record ID")
    grant_id: str = Field(..., description="Redeemed grant ID")
    tool_name: str = Field(..., description="Tool executed")
    agent_id: str = Field(..., description="Executing agent")
    timestamp: float = Field(..., description="Usage timestamp")
    task_id: str | None = Field(default=None, description="Task context")
    session_id: str = Field(..., description="Session context")


class AuditLedgerResponseDTO(BaseModel):
    """Collection of recorded grant usages."""

    records: list[GrantUsageRecordDTO] = Field(..., description="Audit records")


class ScopedApprovalMetricsDTO(BaseModel):
    """Operational metrics for scoped approval gates."""

    evaluations_total: int = Field(..., description="Total gate evaluations")
    silent_allows_total: int = Field(..., description="Total silent allows")
    asks_required_total: int = Field(..., description="Total confirmations requested")
    denials_total: int = Field(..., description="Total hard denials")
    grants_issued_total: int = Field(..., description="Total leases issued")
    grants_revoked_total: int = Field(..., description="Total leases revoked")
    grant_redemptions_total: int = Field(..., description="Total lease redemptions")
