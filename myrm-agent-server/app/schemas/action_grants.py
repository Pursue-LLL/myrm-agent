"""Pydantic schemas for Scoped Time-Bounded Action Grant Registry and Trust Budget.

[INPUT]
Standard library typing Literal, pydantic BaseModel and Field.

[OUTPUT]
GrantEvaluationStatusType, CreateActionGrantRequest, ActionGrantResponse,
ActionGrantConsumeRequest, ActionGrantConsumeResponse, ActionGrantRevokeRequest,
ActionGrantRevokeResponse, AgentTrustBudgetResponse.

[POS]
Schema contracts for time-bounded and tool-scoped action permission grants and agent trust budgets.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

GrantEvaluationStatusType = Literal[
    "granted",
    "expired",
    "exhausted",
    "revoked",
    "mismatch_agent",
    "not_found",
]


class CreateActionGrantRequest(BaseModel):
    """Payload to issue a four-dimensional action grant for an agent."""

    agent_id: str = Field(..., description="Target agent holding the grant")
    service: str = Field(..., description="Target connector or service name")
    action: str = Field(..., description="Action verb category")
    transaction: str = Field(
        default="*", description="Transaction anchor ID or wildcard '*'"
    )
    ttl_seconds: float = Field(
        default=3600.0, description="Validity time window in seconds"
    )
    max_uses: int | None = Field(
        default=None, description="Optional maximum usage quota limit"
    )


class ActionGrantResponse(BaseModel):
    """Representation of an active or revoked 4D action grant."""

    grant_id: str = Field(..., description="Unique grant identifier")
    agent_id: str = Field(..., description="Agent bound to this grant")
    service: str = Field(..., description="Target service")
    action: str = Field(..., description="Action verb category")
    transaction: str = Field(..., description="Transaction anchor identifier")
    valid_from: float = Field(..., description="Valid start timestamp")
    expires_at: float = Field(..., description="Expiration timestamp")
    max_uses: int | None = Field(None, description="Maximum execution limit")
    used_count: int = Field(0, description="Current consumption count")
    is_revoked: bool = Field(False, description="Monotonic revocation flag")
    revocation_reason: str | None = Field(None, description="Revocation rationale")
    created_at: float = Field(..., description="Creation timestamp")


class EvaluateActionGrantRequest(BaseModel):
    """Payload to evaluate whether an upcoming agent invocation matches an active grant."""

    agent_id: str = Field(..., description="Calling agent ID")
    service: str = Field(..., description="Target service")
    action: str = Field(..., description="Action verb")
    transaction: str = Field(..., description="Transaction object identifier")


class EvaluateActionGrantResponse(BaseModel):
    """Evaluation outcome for pre-action grant check."""

    is_granted: bool = Field(..., description="Whether grant allows direct passthrough")
    status: GrantEvaluationStatusType = Field(
        ..., description="Evaluation status categorization"
    )
    grant_id: str | None = Field(None, description="ID of matched grant if any")
    reason: str = Field(..., description="Explanation of evaluation decision")


class RevokeActionGrantRequest(BaseModel):
    """Payload to explicitly revoke an individual grant."""

    grant_id: str = Field(..., description="Grant ID to revoke")
    reason: str = Field(
        default="Explicit user revocation",
        description="Reason for revoking grant",
    )


class CascadeReclaimRequest(BaseModel):
    """Payload to cascade reclaim grants by service connector or agent."""

    service: str | None = Field(
        None, description="Cascade revoke all grants for this service connector"
    )
    agent_id: str | None = Field(
        None, description="Cascade revoke all grants for this agent"
    )
    reason: str = Field(
        default="Cascade reclamation triggered",
        description="Reason for cascade cleanup",
    )


class CascadeReclaimResponse(BaseModel):
    """Response returned upon executing cascade reclamation."""

    revoked_count: int = Field(..., description="Total grants revoked")
    message: str = Field(..., description="Outcome message")


class TrustBudgetResponse(BaseModel):
    """Cumulative trust budget status for an agent x service x action tuple."""

    agent_id: str = Field(..., description="Agent identifier")
    service: str = Field(..., description="Service identifier")
    action: str = Field(..., description="Action verb")
    consecutive_approvals: int = Field(
        ..., description="Consecutive uncorrected user approvals"
    )
    is_locked_to_ask: bool = Field(
        ..., description="Whether dimension is locked to Ask mode"
    )
    should_suggest_grant: bool = Field(
        ..., description="Whether threshold met to suggest creating a grant"
    )


class RecordApprovalRequest(BaseModel):
    """Payload to record a successful user approval without correction."""

    agent_id: str = Field(..., description="Agent identifier")
    service: str = Field(..., description="Service identifier")
    action: str = Field(..., description="Action verb")


class RecordDemotionRequest(BaseModel):
    """Payload to record a user correction, collapse trust to 0, and lock to Ask."""

    agent_id: str = Field(..., description="Agent identifier")
    service: str = Field(..., description="Service identifier")
    action: str = Field(..., description="Action verb")
    reason: str = Field(
        default="User corrected or revoked action",
        description="Demotion rationale",
    )
