"""Pydantic schemas and DTOs for Dialectic Liveness Guard & Stale Pivot Discard (Item 116).

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- DialecticLivenessConfigDTO, LivenessTelemetryDTO, DialecticAuditLogDTO: guard configuration, live telemetry and audit entries
- ShouldTrigger, SubmitResult, ConsumePending and NotifyMutation request/response models: dialectic cycle payloads

[POS]
API contracts of the dialectic liveness guard, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DialecticLivenessConfigDTO(BaseModel):
    """Configuration DTO for dialectic liveness, pivots, and backoff."""

    base_cadence: int = Field(default=5, ge=1, description="Base turn cadence between triggers")
    timeout_seconds: float = Field(default=30.0, gt=0.0, description="Baseline inference timeout seconds")
    stale_thread_multiplier: float = Field(default=2.0, ge=1.0, description="Multiplier before hung thread is declared dead")
    stale_result_multiplier: float = Field(default=2.0, ge=1.0, description="Multiplier before conversational pivot invalidates result")
    max_backoff_multiplier: int = Field(default=8, ge=1, description="Maximum backoff multiplier for empty streaks")


class DialecticAuditLogDTO(BaseModel):
    """DTO representing an audit log entry for dialectic lifecycle events."""

    event_id: str = Field(description="Unique event identifier")
    session_id: str = Field(description="Session identifier")
    action: str = Field(description="Action name (e.g. cycle_triggered, stale_pivot_discarded)")
    turn: int = Field(description="Turn index when event occurred")
    detail: str = Field(description="Diagnostic details")
    timestamp_monotonic: float = Field(description="Monotonic clock timestamp")


class LivenessTelemetryDTO(BaseModel):
    """Telemetry DTO capturing dialectic slot state and backoff metrics."""

    session_id: str = Field(description="Session identifier")
    current_turn: int = Field(description="Current session turn")
    effective_cadence: int = Field(description="Current effective cadence including backoff")
    empty_streak: int = Field(description="Consecutive empty inference outcomes count")
    slot_state: str = Field(description="Current slot state: idle, running, dead, completed")
    active_cycle_token: int = Field(description="Active generation token for cycle")
    total_fires: int = Field(default=0, description="Total number of inference cycles triggered")
    dead_threads_recovered: int = Field(default=0, description="Count of hung dead threads recovered")
    stale_pivots_discarded: int = Field(default=0, description="Count of stale pivot results discarded")
    stale_tokens_rejected: int = Field(default=0, description="Count of rejected late orphan returns")
    successful_consumptions: int = Field(default=0, description="Count of fresh results successfully consumed")
    audit_events: list[DialecticAuditLogDTO] = Field(default_factory=list, description="Recent audit trail entries")


class ShouldTriggerRequest(BaseModel):
    """Request payload to evaluate trigger readiness and allocate cycle token."""

    session_id: str = Field(min_length=1, description="Session identifier")
    current_turn: int = Field(ge=0, description="Current turn index")
    now_mono: float | None = Field(default=None, description="Optional override for monotonic clock")


class ShouldTriggerResponse(BaseModel):
    """Response payload for trigger evaluation."""

    should_trigger: bool = Field(description="Whether a new dialectic cycle should be launched")
    cycle_token: int | None = Field(default=None, description="Allocated cycle token if triggered")
    effective_cadence: int = Field(description="Current effective cadence")


class SubmitResultRequest(BaseModel):
    """Request payload to submit completed background dialectic inference."""

    session_id: str = Field(min_length=1, description="Session identifier")
    cycle_token: int = Field(description="Generation cycle token matching this execution")
    content: str | None = Field(default=None, description="Inference content, or None/empty for no-op")
    now_mono: float | None = Field(default=None, description="Optional override for monotonic clock")


class SubmitResultResponse(BaseModel):
    """Response payload for inference submission."""

    accepted: bool = Field(description="Whether the result was accepted (False if orphan zombie token)")
    staged: bool = Field(description="Whether non-empty content was staged pending consumption")


class ConsumePendingRequest(BaseModel):
    """Request payload to consume staged dialectic result or discard on pivot."""

    session_id: str = Field(min_length=1, description="Session identifier")
    current_turn: int = Field(ge=0, description="Current turn index")


class ConsumePendingResponse(BaseModel):
    """Response payload for pending dialectic result consumption."""

    has_content: bool = Field(description="Whether fresh content was retrieved")
    content: str | None = Field(default=None, description="Fresh content, or None if omitted or discarded")


class NotifyMutationRequest(BaseModel):
    """Request payload to notify critical mutation event and reset backoff."""

    session_id: str = Field(min_length=1, description="Session identifier")
    reason: str = Field(default="", description="Reason or source of mutation")


class NotifyMutationResponse(BaseModel):
    """Response payload acknowledging mutation notification."""

    success: bool = Field(default=True, description="Whether streak was reset")
    effective_cadence: int = Field(description="Effective cadence restored to baseline")
