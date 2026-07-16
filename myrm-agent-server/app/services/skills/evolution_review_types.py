"""
[INPUT]
- app.database.models.approval::ApprovalRecord (POS: 统一审批记录模型)
[OUTPUT]
- Evolution growth/apply enums, approval payload models, review record DTO, payload normalization helpers
[POS]
Evolution 审核域类型与 ApprovalRecord ↔ review record 转换（无 I/O）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field, ValidationError

from app.database.models import ApprovalRecord
from app.services.skills.experience_ledger import ExperienceEventType

logger = logging.getLogger(__name__)

EVOLUTION_ACTION_TYPE = "evolution"
MAX_SKILL_CONTENT_CHARS = 65_536


class EvolutionGrowthStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    FAILED_SCAN = "FAILED_SCAN"
    BLOCKED_LOCKED = "BLOCKED_LOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLY_FAILED = "APPLY_FAILED"


PENDING_EVOLUTION_GROWTH_STATUSES: tuple[str, ...] = (
    EvolutionGrowthStatus.PENDING_REVIEW.value,
    EvolutionGrowthStatus.APPLY_FAILED.value,
)


class EvolutionApplyStatus(StrEnum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class RuntimeFailureEvidence(BaseModel):
    source: str = "runtime"
    tool_name: str
    error_signature: str
    tool_args_hash: str | None = None
    loop_kind: str | None = None
    skill_version: str | None = None
    attribution_confidence: float
    failure_count: int = 1
    first_seen_at: str
    last_seen_at: str
    candidate_skill_names: list[str] = Field(default_factory=list)


class EvolutionApprovalPayload(BaseModel):
    schema_version: int = 1
    skill_id: str
    skill_name: str
    skill_path: str
    evolution_type: str
    reason: str
    original_content: str
    evolved_content: str
    confidence: float
    test_passed: bool
    task_context: str | None = None
    trajectory: str | None = None
    growth_status: EvolutionGrowthStatus = EvolutionGrowthStatus.PENDING_REVIEW
    apply_status: EvolutionApplyStatus = EvolutionApplyStatus.NOT_APPLIED
    apply_error: str | None = None
    reject_reason: str | None = None
    reason_code: str | None = "manual_review"
    remediation: str | None = "Review the diff and approve or reject the proposal."
    runtime_failure: RuntimeFailureEvidence | None = None


@dataclass(slots=True)
class EvolutionReviewRecord:
    id: str
    source: str
    skill_id: str
    skill_name: str
    skill_path: str
    evolution_type: str
    reason: str
    original_content: str
    evolved_content: str
    confidence: float
    test_passed: bool
    status: EvolutionGrowthStatus
    approval_status: str
    apply_status: EvolutionApplyStatus
    apply_error: str | None
    reason_code: str | None
    remediation: str | None
    runtime_failure: RuntimeFailureEvidence | None
    trajectory: str | None
    chat_id: str | None
    task_context: str | None
    created_at: datetime
    resolved_at: datetime | None


class EvolutionApplyError(RuntimeError):
    """Raised when an approved evolution could not be applied to disk."""


def evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"


def apply_failure_remediation(skill_name: str) -> str:
    return (
        f'Resolve the file-system issue for "{skill_name}" and retry apply, or reject the proposal if the change should not land.'
    )


def approval_payload(record: ApprovalRecord) -> EvolutionApprovalPayload | None:
    raw_payload = record.payload if isinstance(record.payload, dict) else {}
    try:
        return EvolutionApprovalPayload.model_validate(raw_payload)
    except ValidationError as exc:
        logger.error("Failed to parse evolution approval payload for %s: %s", record.id, exc)
        return None


def approval_to_evolution_review_record(
    record: ApprovalRecord,
) -> EvolutionReviewRecord | None:
    if record.action_type != EVOLUTION_ACTION_TYPE:
        return None
    payload = approval_payload(record)
    if payload is None:
        return None
    return EvolutionReviewRecord(
        id=record.id,
        source="approval",
        skill_id=payload.skill_id,
        skill_name=payload.skill_name,
        skill_path=payload.skill_path,
        evolution_type=payload.evolution_type,
        reason=payload.reason,
        original_content=payload.original_content,
        evolved_content=payload.evolved_content,
        confidence=payload.confidence,
        test_passed=payload.test_passed,
        status=payload.growth_status,
        approval_status=record.status,
        apply_status=payload.apply_status,
        apply_error=payload.apply_error,
        reason_code=payload.reason_code,
        remediation=payload.remediation,
        runtime_failure=payload.runtime_failure,
        trajectory=payload.trajectory,
        chat_id=record.chat_id,
        task_context=payload.task_context,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
    )


def runtime_failure_ledger_event(
    growth_status: EvolutionGrowthStatus,
) -> ExperienceEventType:
    if growth_status == EvolutionGrowthStatus.FAILED_SCAN:
        return ExperienceEventType.SKILL_GROWTH_FAILED_SCAN
    if growth_status == EvolutionGrowthStatus.BLOCKED_LOCKED:
        return ExperienceEventType.SKILL_GROWTH_BLOCKED
    if growth_status == EvolutionGrowthStatus.REJECTED:
        return ExperienceEventType.EVOLUTION_REJECTED
    return ExperienceEventType.EVOLUTION_PENDING


def creation_outcome(growth_status: EvolutionGrowthStatus) -> str:
    if growth_status == EvolutionGrowthStatus.PENDING_REVIEW:
        return "pending"
    return growth_status.value.lower()
