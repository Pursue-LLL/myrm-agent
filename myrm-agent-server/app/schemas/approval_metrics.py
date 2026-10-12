"""Pydantic schemas for Approval False Positive Metric Loop.

[INPUT]
- None.

[OUTPUT]
- Typed DTO models for recording classifier verdicts, submitting review feedback, and querying FPR metrics.

[POS]
- Server schemas. Exposes typed contracts for approval false positive observability and rule feedback loops.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class RecordVerdictRequest(BaseModel):
    """Payload to record a classifier decision."""

    model_config = ConfigDict(extra="forbid")

    command: str = Field(..., description="Action or CLI command evaluated")
    decision: Literal["allow", "deny", "uncertain"] = Field(
        ..., description="Classifier decision outcome"
    )
    reason: str = Field(..., description="Brief rationale explaining the decision")
    workspace_root: str | None = Field(
        default=None, description="Workspace directory context"
    )
    taint_labels: list[str] = Field(
        default_factory=list, description="Active taint labels present during classification"
    )
    timestamp: float | None = Field(
        default=None, description="Optional unix timestamp override"
    )
    audit_id: str | None = Field(
        default=None, description="Optional explicit audit log identifier"
    )


class RecordVerdictResponse(BaseModel):
    """Receipt confirming classifier verdict record."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Unique audit log identifier")
    timestamp: float = Field(..., description="Unix timestamp of evaluation")
    command: str = Field(..., description="Action evaluated")
    decision: str = Field(..., description="Decision outcome")
    reason: str = Field(..., description="Rationale explanation")
    feedback: str = Field(..., description="Initial feedback status (default: unreviewed)")


class SubmitVerdictFeedbackRequest(BaseModel):
    """Payload to submit ground-truth human feedback on a verdict."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Target audit log identifier")
    feedback: Literal["true_positive", "false_positive", "confirmed_safe"] = Field(
        ..., description="Adjudicated human review outcome"
    )
    feedback_reason: str = Field(
        ..., description="Operator rationale explaining why verdict was overturned or confirmed"
    )


class SubmitVerdictFeedbackResponse(BaseModel):
    """Receipt confirming feedback ingestion."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether feedback was successfully applied")
    audit_id: str = Field(..., description="Target audit log identifier")
    feedback: str = Field(..., description="Applied feedback outcome")


class GetFprMetricResponse(BaseModel):
    """Aggregated empirical False Positive Rate (FPR) metrics."""

    model_config = ConfigDict(extra="forbid")

    window_seconds: float = Field(..., description="Sliding calculation time window in seconds")
    total_evaluations: int = Field(..., description="Total classified operations in window")
    total_blocks_or_asks: int = Field(..., description="Total blocked or interrupted actions")
    confirmed_false_positives: int = Field(..., description="Count of confirmed false positive blocks")
    confirmed_true_positives: int = Field(..., description="Count of confirmed true positive blocks")
    false_positive_rate: float = Field(
        ..., description="Empirical false positive rate (confirmed_fps / total_blocks_or_asks)"
    )
    alert_threshold: float = Field(..., description="Configured alert threshold ratio")
    is_alerting: bool = Field(..., description="Whether current FPR exceeds safety threshold")


class FalsePositiveSampleDto(BaseModel):
    """Extracted false positive sample for rule tuning."""

    model_config = ConfigDict(extra="forbid")

    audit_id: str = Field(..., description="Audit log identifier")
    timestamp: float = Field(..., description="Unix timestamp of evaluation")
    command: str = Field(..., description="Action incorrectly blocked or interrupted")
    decision: str = Field(..., description="Classifier decision")
    original_reason: str = Field(..., description="Original classifier reason")
    feedback_reason: str = Field(..., description="Human review rationale")
    suggested_rule_tuning: str = Field(..., description="Actionable suggestion for rule adjustments")


class ExportFalsePositiveSamplesResponse(BaseModel):
    """Collection of false positive samples for tuning loop."""

    model_config = ConfigDict(extra="forbid")

    samples: list[FalsePositiveSampleDto] = Field(
        default_factory=list, description="False positive sample list"
    )
    total_count: int = Field(..., description="Total returned samples count")
