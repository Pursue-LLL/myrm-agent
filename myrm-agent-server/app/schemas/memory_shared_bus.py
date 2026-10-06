"""
[POS] app/schemas/memory_shared_bus.py
[INPUT] pydantic
[OUTPUT] NegativeDecisionCreateRequestDTO, NegativeDecisionDTO, NegativeDecisionCheckRequestDTO, NegativeDecisionCheckResponseDTO, ConcurrencyPoolStatusResponseDTO, MemoryScoreRequestDTO, MemoryScoreResponseDTO

Pydantic DTOs for Multi-Agent Shared Memory Bus, Concurrency Pool, Backpressure Guard, and Negative Decision Ledger.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NegativeDecisionCreateRequestDTO(BaseModel):
    """Payload to record a vetoed technical decision into the ledger."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(..., description="Unique decision ID")
    decision_subject: str = Field(..., description="Subject or name of the rejected proposal")
    veto_reason: str = Field(..., description="Justification for rejection")
    alternative_chosen: str = Field(..., description="Accepted alternative design")
    context_summary: str = Field(default="", description="Technical context and cost trade-offs")
    severity: str = Field(default="hard_block", description="Severity level: hard_block, warning, advisory")
    scope: str = Field(default="global", description="Scope: global, project, or agent_role")


class NegativeDecisionDTO(BaseModel):
    """DTO representing a stored negative decision ledger entry."""

    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(..., description="Unique decision ID")
    decision_subject: str = Field(..., description="Subject or name of the rejected proposal")
    veto_reason: str = Field(..., description="Justification for rejection")
    alternative_chosen: str = Field(..., description="Accepted alternative design")
    context_summary: str = Field(default="", description="Technical context")
    severity: str = Field(..., description="Severity level")
    scope: str = Field(..., description="Scope")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class NegativeDecisionCheckRequestDTO(BaseModel):
    """Payload to check whether a candidate proposal conflicts with vetoed history."""

    model_config = ConfigDict(extra="forbid")

    candidate_proposal: str = Field(..., description="Candidate design proposal to screen")
    scope: str = Field(default="global", description="Screening scope")


class NegativeDecisionCheckResponseDTO(BaseModel):
    """Response detailing screening results against the negative decision ledger."""

    model_config = ConfigDict(extra="forbid")

    is_blocked: bool = Field(..., description="True if proposal is strictly prohibited")
    matched_entries: list[NegativeDecisionDTO] = Field(
        default_factory=list, description="Conflicting veto records"
    )
    guard_prompt_slice: str = Field(
        default="", description="Instructional prompt slice for model injection"
    )
    rejection_summary: str = Field(
        default="", description="Concise human-readable conflict justification"
    )


class ConcurrencyPoolStatusResponseDTO(BaseModel):
    """DTO presenting live health and backpressure metrics of the shared memory bus."""

    model_config = ConfigDict(extra="forbid")

    active_readers: int = Field(..., ge=0, description="Active concurrent reader count")
    active_writers: int = Field(..., ge=0, description="Active concurrent writer count")
    queued_tasks: int = Field(..., ge=0, description="Number of tasks queued for access")
    current_rss_mb: float = Field(..., ge=0.0, description="Process RSS memory usage in MB")
    is_throttled: bool = Field(..., description="True if backpressure rate-limiting is active")
    status_message: str = Field(..., description="Operational status descriptor")


class MemoryScoreRequestDTO(BaseModel):
    """Payload to evaluate access frequency reinforcement and half-life decay score."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Target memory ID")
    content: str = Field(..., description="Memory factual content")
    base_weight: float = Field(default=1.0, gt=0.0, description="Base baseline weight")
    hit_count: int = Field(default=0, ge=0, description="Cumulative retrieval hit count")
    last_accessed_at: str | None = Field(
        default=None, description="ISO timestamp of last retrieval access"
    )


class MemoryScoreResponseDTO(BaseModel):
    """Composite ranking score calculated by the reinforced decay self-learning engine."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Target memory ID")
    content: str = Field(..., description="Memory factual content")
    base_weight: float = Field(..., description="Base baseline weight")
    hit_count: int = Field(..., description="Cumulative retrieval hit count")
    last_accessed_at: str = Field(..., description="ISO timestamp of access")
    composite_score: float = Field(..., description="Final combined score")
    decay_factor: float = Field(..., description="Temporal decay multiplier")
    reinforcement_factor: float = Field(..., description="Hit count reinforcement multiplier")
