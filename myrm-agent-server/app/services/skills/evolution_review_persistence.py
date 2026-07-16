"""
[INPUT]
- app.database.models.approval::ApprovalRecord
- app.services.skills.evolution_review_types::EvolutionApprovalPayload
[OUTPUT]
- load/list/count/persist helpers for evolution ApprovalRecord rows
[POS]
Evolution 审核 ApprovalRecord 持久化读写（list/count 在 SQL 层应用 action_type、pending growth_status 与 LIMIT）。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import desc, func, or_, select

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.skills.evolution_review_types import (
    EVOLUTION_ACTION_TYPE,
    PENDING_EVOLUTION_GROWTH_STATUSES,
    EvolutionApprovalPayload,
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    approval_payload,
    approval_to_evolution_review_record,
)


def _pending_growth_status_clause():
    growth_status = ApprovalRecord.payload["growth_status"].as_string()
    return or_(
        growth_status.in_(PENDING_EVOLUTION_GROWTH_STATUSES),
        growth_status.is_(None),
    )


async def load_approval_record(evolution_id: str) -> ApprovalRecord | None:
    async with get_session() as db:
        record = await db.get(ApprovalRecord, evolution_id)
        if record is None or record.action_type != EVOLUTION_ACTION_TYPE:
            return None
        return record


async def persist_approval_payload(
    evolution_id: str,
    *,
    approval_status: str | None = None,
    payload: EvolutionApprovalPayload | None = None,
    resolved_at: datetime | None | object = ...,
) -> ApprovalRecord:
    async with get_session() as db:
        record = await db.get(ApprovalRecord, evolution_id)
        if record is None or record.action_type != EVOLUTION_ACTION_TYPE:
            raise RuntimeError(f"Evolution approval record not found: {evolution_id}")
        if approval_status is not None:
            record.status = approval_status
        if payload is not None:
            record.payload = payload.model_dump(mode="json")
        if resolved_at is not ...:
            record.resolved_at = resolved_at
        await db.commit()
        await db.refresh(record)
        return record


async def list_approval_review_records(
    *,
    limit: int | None = None,
    pending_only: bool = False,
) -> list[EvolutionReviewRecord]:
    async with get_session() as db:
        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
            .order_by(desc(ApprovalRecord.created_at))
        )
        if pending_only:
            stmt = stmt.where(_pending_growth_status_clause())
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await db.execute(stmt)
        records = list(result.scalars().all())
    items: list[EvolutionReviewRecord] = []
    for record in records:
        review_record = approval_to_evolution_review_record(record)
        if review_record is not None:
            items.append(review_record)
    return items


async def count_approval_review_records(*, pending_only: bool = False) -> int:
    async with get_session() as db:
        stmt = (
            select(func.count())
            .select_from(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
        )
        if pending_only:
            stmt = stmt.where(_pending_growth_status_clause())
        result = await db.execute(stmt)
        return result.scalar() or 0


async def find_matching_approval_records(
    *,
    skill_id: str,
    error_signature: str,
    skill_version: str | None,
) -> list[ApprovalRecord]:
    async with get_session() as db:
        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
            .where(ApprovalRecord.payload["skill_id"].as_string() == skill_id)
            .where(ApprovalRecord.payload["runtime_failure"]["error_signature"].as_string() == error_signature)
            .order_by(desc(ApprovalRecord.created_at))
        )
        if skill_version is not None:
            stmt = stmt.where(ApprovalRecord.payload["runtime_failure"]["skill_version"].as_string() == skill_version)
        result = await db.execute(stmt)
        return list(result.scalars().all())


def filter_runtime_failure_record(
    records: list[ApprovalRecord],
    *,
    skill_id: str,
    error_signature: str,
    skill_version: str | None,
    open_statuses: set[EvolutionGrowthStatus],
) -> EvolutionReviewRecord | None:
    for record in records:
        payload = approval_payload(record)
        if payload is None or payload.runtime_failure is None:
            continue
        if payload.skill_id != skill_id:
            continue
        if payload.runtime_failure.error_signature != error_signature:
            continue
        if skill_version is not None and payload.runtime_failure.skill_version != skill_version:
            continue
        if payload.growth_status in open_statuses:
            return approval_to_evolution_review_record(record)
    return None
