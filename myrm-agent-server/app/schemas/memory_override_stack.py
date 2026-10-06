"""
[POS] app/schemas/memory_override_stack.py
[INPUT] pydantic
[OUTPUT] OverrideCandidateRuleDTO, EphemeralBypassRecordDTO, EvaluateOverrideStackRequestDTO, EvaluateOverrideStackResponseDTO

Pydantic DTOs for Playbook Dynamic User Override Stack and Ephemeral Bypass Gate.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class OverrideCandidateRuleDTO(BaseModel):
    """Candidate procedural rule evaluated against the override stack."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique rule identifier")
    action: str = Field(..., description="Action mandated or restricted by the rule")
    trigger: str = Field(default="", description="Trigger condition for rule invocation")
    content: str = Field(default="", description="Full rule description or context")
    facets: list[str] = Field(
        default_factory=lambda: ["global"], description="Rule domain facets"
    )
    is_active: bool = Field(default=True, description="Whether rule is currently active")


class EphemeralBypassRecordDTO(BaseModel):
    """Audit record for a procedural rule temporarily bypassed in the current turn."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Identifier of the bypassed rule")
    rule_action: str = Field(..., description="Action text of the bypassed rule")
    conflicting_clause: str = Field(
        ..., description="User prompt clause triggering the bypass"
    )
    bypass_reason: str = Field(..., description="Explanation of why rule was bypassed")
    bypassed_in_current_turn: bool = Field(
        default=True, description="Flag confirming ephemeral bypass for current turn"
    )


class EvaluateOverrideStackRequestDTO(BaseModel):
    """Payload to evaluate prompt priority and resolve acute procedural conflicts."""

    model_config = ConfigDict(extra="forbid")

    turn_prompt: str = Field(
        ..., description="User turn prompt carrying Level 1 explicit intent"
    )
    candidate_rules: list[OverrideCandidateRuleDTO] = Field(
        default_factory=list, description="Candidate procedural rules to evaluate"
    )
    session_decisions: list[str] | None = Field(
        default=None, description="Optional Level 2 session ephemeral decisions"
    )


class EvaluateOverrideStackResponseDTO(BaseModel):
    """Outcome of override stack priority resolution and ephemeral bypass gating."""

    model_config = ConfigDict(extra="forbid")

    active_rule_ids: list[str] = Field(
        default_factory=list, description="IDs of rules remaining active for injection"
    )
    bypassed_records: list[EphemeralBypassRecordDTO] = Field(
        default_factory=list, description="Audit records of temporarily bypassed rules"
    )
    injected_context_note: str = Field(
        default="", description="Transparent audit notice injected into context"
    )
    has_conflicts: bool = Field(
        default=False, description="Whether any rule was bypassed due to prompt primacy"
    )
