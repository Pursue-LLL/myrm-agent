"""Pydantic schemas for Idle & Budget Gated Auto-Memory Consolidation Suite.

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- AutoMemoryGatingConfigDTO: gating thresholds (idle timeout, minimum turns, information density, remaining budget, cost ratio)
- TurnGatingDecisionDTO, BudgetGatingDecisionDTO, IdleDetectionStateDTO, OverallGatingReportDTO: per-gate decisions and the combined gating report
- SixDimensionalMemoryArtifactDTO: consolidated memory artifact of one session
- EvaluateGatingRequest, EvaluateGatingResponse, ConsolidateSessionRequest, ConsolidateSessionResponse, UpdateGatingConfigRequest: endpoint payloads

[POS]
API contracts of idle- and budget-gated auto-memory consolidation, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class AutoMemoryGatingConfigDTO(BaseModel):
    """Configuration DTO regulating triggers and admission gates."""

    enabled: bool = Field(True, description="Global switch for background distillation.")
    idle_timeout_seconds: float = Field(900.0, ge=10.0, description="Inactivity threshold in seconds.")
    min_turn_count: int = Field(3, ge=1, description="Minimum turns required before consolidation.")
    min_info_density: float = Field(0.35, ge=0.0, le=1.0, description="Minimum information density floor.")
    min_remaining_budget_tokens: int = Field(1000, ge=0, description="Safe token balance floor.")
    max_consolidation_cost_ratio: float = Field(0.25, gt=0.0, le=1.0, description="Max allowed cost ratio.")


class TurnGatingDecisionDTO(BaseModel):
    """Dialogue turn and information density evaluation."""

    passed: bool = Field(..., description="Whether turn & info gain criteria passed.")
    turn_count: int = Field(..., ge=0, description="Detected dialogue turns.")
    info_density: float = Field(..., ge=0.0, le=1.0, description="Computed information density.")
    reason: str = Field(..., description="Diagnostic explanation.")


class BudgetGatingDecisionDTO(BaseModel):
    """Token reserve safety and quota protection evaluation."""

    passed: bool = Field(..., description="Whether budget criteria passed.")
    remaining_tokens: int = Field(..., ge=0, description="Available token balance.")
    estimated_cost_tokens: int = Field(..., ge=0, description="Estimated distillation token cost.")
    cost_ratio: float = Field(..., ge=0.0, description="Cost relative to balance.")
    reason: str = Field(..., description="Diagnostic explanation.")


class IdleDetectionStateDTO(BaseModel):
    """Session inactivity duration inspection."""

    session_id: str = Field(..., description="Session identifier.")
    idle_seconds: float = Field(..., ge=0.0, description="Elapsed seconds since last action.")
    idle_threshold_seconds: float = Field(..., ge=0.0, description="Configured timeout requirement.")
    is_idle_triggered: bool = Field(..., description="True if elapsed time meets threshold.")
    reason: str = Field(..., description="Status summary.")


class OverallGatingReportDTO(BaseModel):
    """Consolidated admission decision bundle."""

    session_id: str = Field(..., description="Session identifier.")
    should_consolidate: bool = Field(..., description="Authoritative verdict.")
    turn_decision: TurnGatingDecisionDTO = Field(..., description="Turn gate breakdown.")
    budget_decision: BudgetGatingDecisionDTO = Field(..., description="Budget gate breakdown.")
    idle_state: IdleDetectionStateDTO = Field(..., description="Idle state breakdown.")
    final_rationale: str = Field(..., description="Comprehensive explanation.")


class SixDimensionalMemoryArtifactDTO(BaseModel):
    """Six-dimensional structured long-term memory artifact."""

    artifact_id: str = Field(..., description="Unique deterministic artifact ID.")
    session_id: str = Field(..., description="Originating session identifier.")
    created_at_iso: str = Field(..., description="ISO 8601 creation timestamp.")
    working_directory: str = Field(..., description="Primary workspace/project path.")
    key_topics: list[str] = Field(default_factory=list, description="Core technical topics.")
    user_preferences: list[str] = Field(default_factory=list, description="Preserved user habits.")
    reusable_domain_knowledge: list[str] = Field(default_factory=list, description="Reusable insights.")
    failure_lessons: list[str] = Field(default_factory=list, description="Postmortem debugging lessons.")
    tool_calling_patterns: list[str] = Field(default_factory=list, description="Tool behavioral patterns.")
    token_cost: int = Field(0, ge=0, description="Tokens expended distilling artifact.")
    summary_digest: str = Field(..., description="Concise synopsis across dimensions.")


class EvaluateGatingRequest(BaseModel):
    """Request payload to inspect admission gates for a session."""

    session_id: str = Field(..., description="Target session identifier.")
    messages: list[dict[str, str]] = Field(..., description="Conversation messages history.")
    remaining_tokens: int = Field(10000, ge=0, description="Current available token reserve.")
    last_active_timestamp: float = Field(0.0, ge=0.0, description="Epoch timestamp of last interaction.")
    current_timestamp: float | None = Field(None, description="Optional override for current time.")
    require_idle: bool = Field(True, description="Whether idle timeout is strictly required.")


class EvaluateGatingResponse(BaseModel):
    """Response payload containing gating evaluation report."""

    report: OverallGatingReportDTO


class ConsolidateSessionRequest(BaseModel):
    """Request payload to execute gated auto-consolidation."""

    session_id: str = Field(..., description="Target session identifier.")
    messages: list[dict[str, str]] = Field(..., description="Conversation messages history.")
    remaining_tokens: int = Field(10000, ge=0, description="Current available token reserve.")
    working_directory: str = Field("/workspace", description="Project working directory.")
    tool_call_records: list[str] = Field(default_factory=list, description="Tool invocation telemetry.")
    last_active_timestamp: float = Field(0.0, ge=0.0, description="Epoch timestamp of last interaction.")
    current_timestamp: float | None = Field(None, description="Optional override for current time.")
    force_bypass_gating: bool = Field(False, description="Manual override to bypass admission gates.")
    require_idle: bool = Field(True, description="Whether idle timeout is strictly required.")


class ConsolidateSessionResponse(BaseModel):
    """Response payload with gating report and generated artifact if admitted."""

    report: OverallGatingReportDTO
    artifact: SixDimensionalMemoryArtifactDTO | None = None
    persisted: bool = Field(False, description="Whether artifact was committed to long-term memory.")


class UpdateGatingConfigRequest(BaseModel):
    """Request payload to update runtime gating config."""

    config: AutoMemoryGatingConfigDTO
