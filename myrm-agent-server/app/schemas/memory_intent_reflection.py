"""
[POS] app/schemas/memory_intent_reflection.py
[INPUT] pydantic
[OUTPUT] ClassifyIntentRequestDTO, ClassifyIntentResponseDTO, CandidateRuleDTO, EvaluateActivationRequestDTO, EvaluateActivationResponseDTO

Pydantic DTOs for Lightweight Reflection Intent Filter and Playbook Activation Probe.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ClassifyIntentRequestDTO(BaseModel):
    """Payload to classify user turn query into an intent tier."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="User prompt or turn instruction to classify")
    context_metadata: dict[str, str] | None = Field(
        default=None, description="Optional conversational context metadata"
    )


class ClassifyIntentResponseDTO(BaseModel):
    """Telemetry outcome of intent tier classification."""

    model_config = ConfigDict(extra="forbid")

    tier: str = Field(
        ...,
        description="Intent tier: tier_0_fast_path, tier_1_code_execution, tier_2_knowledge_content, tier_3_deep_reasoning",
    )
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    matched_keywords: list[str] = Field(
        default_factory=list, description="Matched lexical or pattern keywords"
    )
    suggested_facets: list[str] = Field(
        default_factory=list, description="Suggested domain facets to awaken"
    )
    source: str = Field(..., description="Classification source (heuristic or probe)")
    reason: str = Field(..., description="Human-readable decision explanation")


class CandidateRuleDTO(BaseModel):
    """Compact candidate behavioral rule for activation gating."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., description="Unique rule identifier")
    trigger: str = Field(default="", description="Rule trigger pattern")
    action: str = Field(default="", description="Action to execute")
    facets: list[str] = Field(
        default_factory=lambda: ["global"], description="Rule domain facets"
    )
    is_active: bool = Field(default=True, description="Whether rule is operational")
    lifecycle_state: str = Field(
        default="active", description="Lifecycle state (active, degraded, retired)"
    )


class EvaluateActivationRequestDTO(BaseModel):
    """Payload to evaluate query intent and filter candidate procedural playbooks."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="User turn prompt to evaluate")
    candidates: list[CandidateRuleDTO] = Field(
        default_factory=list, description="Candidate procedural rules"
    )
    context_metadata: dict[str, str] | None = Field(
        default=None, description="Optional context metadata"
    )


class EvaluateActivationResponseDTO(BaseModel):
    """Outcome of playbook activation gating and retrieval bypass evaluation."""

    model_config = ConfigDict(extra="forbid")

    tier: str = Field(..., description="Classified intent tier")
    bypass_retrieval: bool = Field(
        ..., description="Whether vector retrieval should be bypassed"
    )
    active_facets: list[str] = Field(
        default_factory=list, description="Active domain facets"
    )
    activated_rule_ids: list[str] = Field(
        default_factory=list, description="IDs of activated rules"
    )
    suppressed_rules_count: int = Field(
        ..., ge=0, description="Count of suppressed candidate rules"
    )
    decision_reason: str = Field(..., description="Explanation of activation decision")
