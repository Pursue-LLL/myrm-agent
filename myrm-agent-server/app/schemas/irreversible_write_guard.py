"""Pydantic schemas for Pre-Flight Irreversible Write Interception and Emergency Kill Switch API.

[INPUT]
- Pydantic BaseModel and Field from pydantic.

[OUTPUT]
- DTO schemas for blast radius cards, contracts, intents, and emergency kill switches.

[POS]
Schema layer defining write interception DTOs and approval review cards.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BlastRadiusCardResponse(BaseModel):
    """Explosion radius card presented for user review before executing irreversible operations."""

    intent_id: str
    domain: str
    title: str
    summary: str
    details: dict[str, str]
    risk_level: str
    created_at: datetime
    expires_at: datetime


class IrreversibleWriteIntentResponse(BaseModel):
    """Execution intent intercepted and suspended awaiting blast radius confirmation."""

    intent_id: str
    session_id: str
    tool_name: str
    domain: str
    arguments: dict[str, str]
    blast_radius: BlastRadiusCardResponse
    status: str
    resolution_reason: str
    created_at: datetime


class InterceptToolCallRequest(BaseModel):
    """Request payload to evaluate and potentially intercept a tool execution."""

    session_id: str = Field(default="default_session", description="Agent session ID")
    tool_name: str = Field(..., description="Tool name to be executed")
    arguments: dict[str, str] = Field(
        default_factory=dict, description="Stringified tool invocation arguments"
    )
    ttl_seconds: int = Field(
        default=300, ge=1, le=86400, description="Expiration window for blast radius review"
    )


class InterceptToolCallResponse(BaseModel):
    """Decision indicating whether execution was suspended for confirmation."""

    intercepted: bool = Field(..., description="Whether action was suspended")
    intent: IrreversibleWriteIntentResponse | None = Field(
        default=None, description="Suspended intent data if intercepted"
    )
    reason: str = Field(..., description="Explanation of decision")


class ApproveIntentRequest(BaseModel):
    """User confirmation approval request for a suspended intent."""

    approver: str = Field(default="user_explicit_dialog", description="Approver identity or context")


class EmergencyKillRequest(BaseModel):
    """Request payload to trigger emergency kill switch on a pending write operation."""

    reason: str = Field(
        default="User triggered Emergency Kill Switch", description="Abort justification"
    )


class EmergencyKillResponse(BaseModel):
    """Outcome of emergency kill switch action."""

    intent_id: str
    killed: bool
    reason: str
    timestamp: datetime


class RegisterContractRequest(BaseModel):
    """Payload to register a new irreversible tool write contract."""

    tool_name: str = Field(..., description="Unique tool identifier")
    domain: str = Field(
        default="email",
        description="Domain category: 'email', 'git_push', 'payment', 'database', 'im_broadcast'",
    )
    description: str = Field(..., description="Human-readable description of tool action")
    default_risk_level: str = Field(
        default="high", description="Risk tier: 'low', 'medium', 'high', 'critical'"
    )


class ContractResponse(BaseModel):
    """Registered irreversible write contract schema."""

    tool_name: str
    domain: str
    description: str
    default_risk_level: str
