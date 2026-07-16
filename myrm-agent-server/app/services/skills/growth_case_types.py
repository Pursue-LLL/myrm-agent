"""[INPUT]
- app.services.skills.evolution_reviews::RuntimeFailureEvidence (POS: runtime failure evidence DTO)

[OUTPUT]
- SkillGrowthCaseSource: enum for case origin (draft vs evolution)
- SkillGrowthCaseStatus: enum for case lifecycle status
- SkillGrowthCaseSummaryRead: list-view DTO
- SkillGrowthCaseDetailRead: detail-view DTO

[POS]
Skill growth case DTOs and enums: summary (list) vs detail (single fetch).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.services.skills.evolution_reviews import RuntimeFailureEvidence


class SkillGrowthCaseSource(StrEnum):
    DRAFT = "draft"
    EVOLUTION = "evolution"


class SkillGrowthCaseStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    AUTO_APPLIED = "AUTO_APPLIED"
    FAILED_SCAN = "FAILED_SCAN"
    BLOCKED_LOCKED = "BLOCKED_LOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLY_FAILED = "APPLY_FAILED"


@dataclass(slots=True)
class SkillGrowthFormMetadataRead:
    schedule_hint: str | None = None
    form_reasoning: str | None = None


@dataclass(slots=True)
class SkillGrowthCaseSummaryRead:
    id: str
    source: SkillGrowthCaseSource
    status: SkillGrowthCaseStatus
    skill_name: str
    skill_id: str | None
    growth_type: str
    title: str
    summary: str
    description: str | None
    confidence: float | None
    test_passed: bool | None
    apply_status: str | None
    apply_error: str | None
    reason_code: str | None
    remediation: str | None
    runtime_failure: RuntimeFailureEvidence | None
    chat_id: str | None
    form_metadata: SkillGrowthFormMetadataRead | None
    has_diff: bool
    has_trajectory: bool
    has_trigger_condition: bool
    has_skill_steps: bool
    created_at: datetime


@dataclass(slots=True)
class SkillGrowthCaseDetailRead:
    id: str
    source: SkillGrowthCaseSource
    status: SkillGrowthCaseStatus
    skill_name: str
    skill_id: str | None
    growth_type: str
    title: str
    summary: str
    description: str | None
    trigger_condition: str | None
    skill_steps: str | None
    original_content: str | None
    proposed_content: str | None
    confidence: float | None
    test_passed: bool | None
    apply_status: str | None
    apply_error: str | None
    reason_code: str | None
    remediation: str | None
    runtime_failure: RuntimeFailureEvidence | None
    trajectory: str | None
    chat_id: str | None
    form_metadata: SkillGrowthFormMetadataRead | None
    created_at: datetime


SkillGrowthCaseRead = SkillGrowthCaseDetailRead
