"""Unified skill growth case queries (approval-backed draft/evolution records)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import case, desc, func, literal, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.skills.evolution_review_types import EVOLUTION_ACTION_TYPE
from app.services.skills.evolution_reviews import (
    EvolutionReviewRecord,
    count_evolution_review_records,
    get_evolution_review_record,
    list_evolution_review_records,
)
from app.services.skills.growth_case_types import (
    SkillGrowthCaseDetailRead,
    SkillGrowthCaseSource,
    SkillGrowthCaseStatus,
    SkillGrowthCaseSummaryRead,
    SkillGrowthFormMetadataRead,
)

_GROWTH_STATUS_VALUES: tuple[str, ...] = tuple(status.value for status in SkillGrowthCaseStatus)

SKILL_GROWTH_CASE_ACTION_TYPES: tuple[str, ...] = (
    "skill_draft",
    "skill_patch",
    "semantic_memory",
)


@dataclass(slots=True)
class SkillGrowthDashboardStatsRead:
    total: int
    pending_review: int
    auto_applied: int
    blocked: int


def _payload_dict(payload: object) -> dict[str, object]:
    return payload if isinstance(payload, dict) else {}


def _text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _float_value(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _bool_value(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _form_metadata(payload: dict[str, object]) -> SkillGrowthFormMetadataRead | None:
    raw = payload.get("form_metadata")
    if not isinstance(raw, dict):
        return None
    schedule_hint = _text(raw.get("schedule_hint"))
    form_reasoning = _text(raw.get("form_reasoning"))
    if schedule_hint is None and form_reasoning is None:
        return None
    return SkillGrowthFormMetadataRead(
        schedule_hint=schedule_hint,
        form_reasoning=form_reasoning,
    )


def _approval_growth_status(record: ApprovalRecord) -> SkillGrowthCaseStatus:
    payload = _payload_dict(record.payload)
    payload_status = _text(payload.get("growth_status"))
    if payload_status is not None:
        try:
            return SkillGrowthCaseStatus(payload_status)
        except ValueError:
            return SkillGrowthCaseStatus.PENDING_REVIEW
    if record.status == "APPROVED":
        return SkillGrowthCaseStatus.APPROVED
    if record.status == "REJECTED":
        return SkillGrowthCaseStatus.REJECTED
    return SkillGrowthCaseStatus.PENDING_REVIEW


def _approval_case_detail(record: ApprovalRecord) -> SkillGrowthCaseDetailRead:
    payload = _payload_dict(record.payload)
    draft_name = _text(payload.get("skill_name")) or record.action_type
    description = _text(record.reason) or _text(payload.get("description"))
    summary = (
        description
        or _text(payload.get("trigger_condition"))
        or _text(payload.get("skill_steps"))
        or _text(payload.get("patch_content"))
        or _text(payload.get("content"))
        or draft_name
    )
    proposed_content = _text(payload.get("patch_content")) or _text(payload.get("content"))
    return SkillGrowthCaseDetailRead(
        id=f"draft:{record.id}",
        source=SkillGrowthCaseSource.DRAFT,
        status=_approval_growth_status(record),
        skill_name=draft_name,
        skill_id=None,
        growth_type=record.action_type,
        title=draft_name,
        summary=summary,
        description=description,
        trigger_condition=_text(payload.get("trigger_condition")),
        skill_steps=_text(payload.get("skill_steps")),
        original_content=None,
        proposed_content=proposed_content,
        confidence=_float_value(payload.get("confidence")),
        test_passed=_bool_value(payload.get("test_passed")),
        apply_status=None,
        apply_error=None,
        reason_code=_text(payload.get("reason_code")),
        remediation=_text(payload.get("remediation")),
        runtime_failure=None,
        trajectory=None,
        chat_id=record.chat_id,
        form_metadata=_form_metadata(payload),
        created_at=record.created_at,
    )


def _evolution_case_detail(record: EvolutionReviewRecord) -> SkillGrowthCaseDetailRead:
    return SkillGrowthCaseDetailRead(
        id=f"evolution:{record.id}",
        source=SkillGrowthCaseSource.EVOLUTION,
        status=SkillGrowthCaseStatus(record.status.value),
        skill_name=record.skill_name,
        skill_id=record.skill_id,
        growth_type=record.evolution_type,
        title=record.skill_name,
        summary=record.reason,
        description=record.reason,
        trigger_condition=None,
        skill_steps=None,
        original_content=record.original_content,
        proposed_content=record.evolved_content,
        confidence=record.confidence,
        test_passed=record.test_passed,
        apply_status=record.apply_status.value,
        apply_error=record.apply_error,
        reason_code=record.reason_code,
        remediation=record.remediation,
        runtime_failure=record.runtime_failure,
        trajectory=record.trajectory,
        chat_id=record.chat_id,
        form_metadata=None,
        created_at=record.created_at,
    )


def detail_to_summary(detail: SkillGrowthCaseDetailRead) -> SkillGrowthCaseSummaryRead:
    return SkillGrowthCaseSummaryRead(
        id=detail.id,
        source=detail.source,
        status=detail.status,
        skill_name=detail.skill_name,
        skill_id=detail.skill_id,
        growth_type=detail.growth_type,
        title=detail.title,
        summary=detail.summary,
        description=detail.description,
        confidence=detail.confidence,
        test_passed=detail.test_passed,
        apply_status=detail.apply_status,
        apply_error=detail.apply_error,
        reason_code=detail.reason_code,
        remediation=detail.remediation,
        runtime_failure=detail.runtime_failure,
        chat_id=detail.chat_id,
        form_metadata=detail.form_metadata,
        has_diff=bool(detail.proposed_content),
        has_trajectory=bool(detail.trajectory),
        has_trigger_condition=bool(detail.trigger_condition),
        has_skill_steps=bool(detail.skill_steps),
        created_at=detail.created_at,
    )


def _approval_case_summary(record: ApprovalRecord) -> SkillGrowthCaseSummaryRead:
    return detail_to_summary(_approval_case_detail(record))


def _evolution_case_summary(record: EvolutionReviewRecord) -> SkillGrowthCaseSummaryRead:
    return detail_to_summary(_evolution_case_detail(record))


def _approval_case(record: ApprovalRecord) -> SkillGrowthCaseDetailRead:
    return _approval_case_detail(record)


def _evolution_case(record: EvolutionReviewRecord) -> SkillGrowthCaseDetailRead:
    return _evolution_case_detail(record)


async def _count_approval_cases() -> int:
    async with get_session() as db:
        result = await db.execute(
            select(func.count())
            .select_from(ApprovalRecord)
            .where(ApprovalRecord.action_type.in_(SKILL_GROWTH_CASE_ACTION_TYPES))
        )
        return int(result.scalar_one())


def _approval_effective_growth_status_expr():
    growth_status = ApprovalRecord.payload["growth_status"].as_string()
    return case(
        (growth_status.in_(_GROWTH_STATUS_VALUES), growth_status),
        (ApprovalRecord.status == "APPROVED", literal(SkillGrowthCaseStatus.APPROVED.value)),
        (ApprovalRecord.status == "REJECTED", literal(SkillGrowthCaseStatus.REJECTED.value)),
        else_=literal(SkillGrowthCaseStatus.PENDING_REVIEW.value),
    )


def _evolution_effective_growth_status_expr():
    growth_status = ApprovalRecord.payload["growth_status"].as_string()
    return case(
        (growth_status.in_(_GROWTH_STATUS_VALUES), growth_status),
        else_=literal(SkillGrowthCaseStatus.PENDING_REVIEW.value),
    )


async def _count_approval_cases_for_statuses(statuses: set[SkillGrowthCaseStatus]) -> int:
    if not statuses:
        return 0
    status_values = {status.value for status in statuses}
    effective_status = _approval_effective_growth_status_expr()
    async with get_session() as db:
        result = await db.execute(
            select(func.count())
            .select_from(ApprovalRecord)
            .where(ApprovalRecord.action_type.in_(SKILL_GROWTH_CASE_ACTION_TYPES))
            .where(effective_status.in_(status_values))
        )
        return int(result.scalar_one())


async def _count_evolution_cases_for_statuses(statuses: set[SkillGrowthCaseStatus]) -> int:
    if not statuses:
        return 0
    status_values = {status.value for status in statuses}
    effective_status = _evolution_effective_growth_status_expr()
    async with get_session() as db:
        result = await db.execute(
            select(func.count())
            .select_from(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
            .where(effective_status.in_(status_values))
        )
        return int(result.scalar_one())


async def _count_cases_for_statuses(statuses: set[SkillGrowthCaseStatus]) -> int:
    approval_count, evolution_count = await asyncio.gather(
        _count_approval_cases_for_statuses(statuses),
        _count_evolution_cases_for_statuses(statuses),
    )
    return approval_count + evolution_count


async def _load_approval_cases(*, limit: int) -> list[SkillGrowthCaseSummaryRead]:
    async with get_session() as db:
        result = await db.execute(
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type.in_(SKILL_GROWTH_CASE_ACTION_TYPES))
            .order_by(desc(ApprovalRecord.created_at))
            .limit(limit)
        )
        records = list(result.scalars().all())
    return [_approval_case_summary(record) for record in records]


async def _load_evolution_cases(*, limit: int) -> list[SkillGrowthCaseSummaryRead]:
    records = await list_evolution_review_records(limit=limit, pending_only=False)
    return [_evolution_case_summary(record) for record in records]


def _merge_fetch_limit(*, limit: int, offset: int) -> int:
    return limit + offset


async def _count_skill_growth_cases(*, status: SkillGrowthCaseStatus | None) -> int:
    if status is None:
        approval_count, evolution_count = await asyncio.gather(
            _count_approval_cases(),
            count_evolution_review_records(pending_only=False),
        )
        return approval_count + evolution_count
    return await _count_cases_for_statuses({status})


async def list_skill_growth_cases(
    *,
    limit: int = 50,
    offset: int = 0,
    status: SkillGrowthCaseStatus | None = None,
) -> tuple[list[SkillGrowthCaseSummaryRead], int]:
    fetch_limit = _merge_fetch_limit(limit=limit, offset=offset)
    approval_cases, evolution_cases = await asyncio.gather(
        _load_approval_cases(limit=fetch_limit),
        _load_evolution_cases(limit=fetch_limit),
    )
    items: list[SkillGrowthCaseSummaryRead] = [*approval_cases, *evolution_cases]
    if status is not None:
        items = [item for item in items if item.status == status]
    items.sort(key=lambda item: item.created_at, reverse=True)
    total = await _count_skill_growth_cases(status=status)
    return items[offset : offset + limit], total


async def get_skill_growth_case_detail(case_id: str) -> SkillGrowthCaseDetailRead | None:
    if case_id.startswith("draft:"):
        record_id = case_id.removeprefix("draft:")
        async with get_session() as db:
            record = await db.get(ApprovalRecord, record_id)
            if record is None or record.action_type not in SKILL_GROWTH_CASE_ACTION_TYPES:
                return None
            return _approval_case_detail(record)

    if case_id.startswith("evolution:"):
        evolution_id = case_id.removeprefix("evolution:")
        record = await get_evolution_review_record(evolution_id)
        if record is None:
            return None
        return _evolution_case_detail(record)

    return None


async def summarize_skill_growth_dashboard_stats() -> SkillGrowthDashboardStatsRead:
    """Return dashboard counters with SQL status bucket counts."""
    pending_statuses = {SkillGrowthCaseStatus.PENDING_REVIEW, SkillGrowthCaseStatus.APPLY_FAILED}
    blocked_statuses = {SkillGrowthCaseStatus.BLOCKED_LOCKED, SkillGrowthCaseStatus.FAILED_SCAN}
    total, pending_review, auto_applied, blocked = await asyncio.gather(
        _count_skill_growth_cases(status=None),
        _count_cases_for_statuses(pending_statuses),
        _count_cases_for_statuses({SkillGrowthCaseStatus.AUTO_APPLIED}),
        _count_cases_for_statuses(blocked_statuses),
    )
    return SkillGrowthDashboardStatsRead(
        total=total,
        pending_review=pending_review,
        auto_applied=auto_applied,
        blocked=blocked,
    )
