"""Pydantic schemas for Three-Tier Stacked Policy Governance and Downgrade Gate.

[INPUT]
- None (Self-contained Pydantic schemas)

[OUTPUT]
- PolicyRuleSchema, EvaluatePolicyRequest, EvaluatePolicyResponse
- DowngradeGateStatusResponse, InjectSessionRuleRequest

[POS]
Schema definitions for stacked policy governance and downgrade gate.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

PolicyTierType = Literal["session", "agent", "server"]
PolicyDecisionType = Literal["allow", "deny", "ask"]
LifecyclePhaseType = Literal["request", "tool_call", "tool_result"]


class PolicyRuleSchema(BaseModel):
    """Declarative policy rule specification."""

    tier: PolicyTierType = Field(..., description="Policy stack hierarchy tier")
    name: str = Field(..., description="Unique rule identifier name")
    phase: LifecyclePhaseType = Field(
        default="tool_call", description="Evaluation lifecycle phase"
    )
    action: PolicyDecisionType = Field(..., description="Evaluation decision")
    target_pattern: str = Field(
        ..., description="Tool or command matching pattern (supports wildcards)"
    )
    reason: str = Field(..., description="Security rationale for rule")
    session_id: str | None = Field(None, description="Bound session ID if tier is session")
    agent_id: str | None = Field(None, description="Bound agent ID if tier is agent")


class EvaluatePolicyRequest(BaseModel):
    """Request payload to evaluate an operation against stacked policies."""

    phase: LifecyclePhaseType = Field(
        default="tool_call", description="Evaluation lifecycle phase"
    )
    target: str = Field(..., description="Operation target or tool name")
    session_id: str | None = Field(None, description="Current session context ID")
    agent_id: str | None = Field(None, description="Current agent context ID")


class AskCardSchema(BaseModel):
    """Interactive MCP-style approval card data emitted for ASK decision."""

    prompt_title: str = Field(..., description="Modal card title")
    target_operation: str = Field(..., description="Target operation requiring approval")
    risk_level: str = Field(..., description="Assessed risk level")
    recommended_action: str = Field(..., description="Recommended user decision")
    context_summary: str = Field(..., description="Context summary of the operation")


class EvaluatePolicyResponse(BaseModel):
    """Outcome of stacked policy evaluation with short-circuit details."""

    decision: PolicyDecisionType = Field(..., description="Final policy decision")
    matched_tier: str | None = Field(None, description="Tier where decision was matched")
    matched_rule: str | None = Field(None, description="Name of rule that made decision")
    reason: str = Field(..., description="Detailed decision rationale")
    requires_approval: bool = Field(
        False, description="Whether operation is suspended waiting for user approval"
    )
    ask_card: AskCardSchema | None = Field(
        None, description="Interactive approval card if decision is ASK"
    )


class InjectSessionRuleRequest(BaseModel):
    """Payload to inject a dynamic session-tier rule."""

    session_id: str = Field(..., description="Target session ID")
    name: str = Field(..., description="Rule name")
    phase: LifecyclePhaseType = Field(
        default="tool_call", description="Lifecycle phase"
    )
    action: PolicyDecisionType = Field(..., description="Decision action")
    target_pattern: str = Field(..., description="Matching pattern")
    reason: str = Field(..., description="Rationale for dynamic session restriction")


class RecordUsageAndDowngradeCheckRequest(BaseModel):
    """Payload to record token/cost delta and evaluate model downgrade status."""

    session_id: str = Field(..., description="Session identifier")
    additional_tokens: int = Field(0, description="Tokens consumed in last step")
    additional_cost: float = Field(0.0, description="USD cost incurred in last step")


class DowngradeGateStatusResponse(BaseModel):
    """Current model routing and threshold enforcement status for a session."""

    session_id: str = Field(..., description="Session identifier")
    is_downgraded: bool = Field(
        ..., description="Whether execution gracefully shifted to economical model"
    )
    is_hard_blocked: bool = Field(
        ..., description="Whether execution is suspended due to hard budget exhaustion"
    )
    active_model: str = Field(..., description="Model currently assigned for session")
    total_tokens: int = Field(..., description="Cumulative session tokens")
    total_cost: float = Field(..., description="Cumulative session cost in USD")
    message: str = Field(..., description="Status explanation message")
