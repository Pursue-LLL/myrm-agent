"""Pydantic V2 schemas for Multi-Perspective Subagent Review & Bounded Review Loop (Item 32).

[INPUT]
- Code diff, architectural context, and round advance payloads.

[OUTPUT]
- Strongly-typed DTOs for multi-perspective reports, round histories, and loop convergence status.

[POS]
- Provides typed data contracts for tri-perspective concurrent reviews,
  remediation tracking, and bounded self-healing iterations.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ReviewPerspectiveEnum(enum.StrEnum):
    """The three specialized review lenses applied concurrently."""

    CORRECTNESS = "correctness"
    TEST_COVERAGE = "test_coverage"
    SIMPLICITY = "simplicity"


class FindingSeverityEnum(enum.StrEnum):
    """Severity classification for review findings."""

    BLOCKER = "blocker"
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    SUGGESTION = "suggestion"


class ReviewLoopStatusEnum(enum.StrEnum):
    """Lifecycle state progression of a bounded review loop."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    FIXING = "fixing"
    CONVERGED = "converged"
    MAX_ROUNDS_REACHED = "max_rounds_reached"


class ReviewFindingDTO(BaseModel):
    """Granular review finding discoverable under a specific lens."""

    model_config = ConfigDict(frozen=True)

    perspective: ReviewPerspectiveEnum
    severity: FindingSeverityEnum
    file_path: str
    issue: str
    suggestion: str
    line_number: int | None = None


class PerspectiveReportDTO(BaseModel):
    """Consolidated assessment from a single perspective reviewer."""

    model_config = ConfigDict(frozen=True)

    perspective: ReviewPerspectiveEnum
    reviewer_name: str
    approved: bool
    findings: list[ReviewFindingDTO] = Field(default_factory=list)
    summary: str = ""


class LoopRoundDTO(BaseModel):
    """Snapshot record of a single review & remediation iteration."""

    model_config = ConfigDict(frozen=True)

    round_number: int
    perspective_reports: dict[str, PerspectiveReportDTO]
    all_findings: list[ReviewFindingDTO]
    has_blocking_issues: bool
    fix_description: str | None = None
    converged: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class StartReviewLoopRequest(BaseModel):
    """Payload to initiate a multi-perspective parallel review loop."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., min_length=1, description="Parent chat session identifier")
    diff_content: str = Field(..., min_length=1, description="Code diff or changes to be reviewed")
    context_description: str | None = Field(
        None,
        description="Optional high-level architectural requirements or task description",
    )
    max_rounds: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Bounded maximum review-worker rounds (default 3)",
    )


class AdvanceReviewLoopRequest(BaseModel):
    """Payload to advance a loop into its next round with updated code diff."""

    model_config = ConfigDict(frozen=True)

    fixed_diff: str = Field(..., min_length=1, description="Remediated code diff")
    fix_note: str | None = Field(
        None,
        description="Human or worker summary of changes made in this round",
    )


class ReviewLoopResponse(BaseModel):
    """Full lifecycle status and iteration history of a review loop."""

    model_config = ConfigDict(frozen=True)

    loop_id: str
    session_id: str
    status: ReviewLoopStatusEnum
    current_round: int
    max_rounds: int
    is_clean: bool
    rounds: list[LoopRoundDTO]
    final_summary: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))


class ReviewLoopListResponse(BaseModel):
    """List of review loops active or archived for a session."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    loops: list[ReviewLoopResponse]
    total_count: int
