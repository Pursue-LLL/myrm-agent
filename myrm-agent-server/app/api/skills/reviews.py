"""
[INPUT]
- app.api.skills.evolution::approve_pending_evolution_record (POS: evolution 审核接口层。对外提供 pending 列表、approve、reject，以 ApprovalRecord 为唯一事实源。)
- app.api.skills.migrations::approve_pending_migration_record (POS: 迁移审核接口层。对外提供 pending migration 的 approve/reject。)
- app.api.memory.utils::get_memory_manager (POS: 记忆接口依赖装配器)
[OUTPUT]
- Unified review inbox APIs
[POS]
统一审核收件箱接口层。聚合 memory / evolution / migration 待审项，并负责审核动作的统一对外契约。
"""

from __future__ import annotations

from enum import StrEnum

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.memory import MemoryManager
from myrm_agent_harness.toolkits.memory.types import PendingRecord
from pydantic import BaseModel, Field

from app.api.memory.utils import get_crud_memory_manager, get_memory_manager
from app.api.skills.evolution import (
    approve_pending_evolution_record,
    count_pending_evolution_records,
    list_pending_evolution_records,
    reject_pending_evolution_record,
)
from app.api.skills.migrations import (
    approve_pending_migration_record,
    count_pending_migration_records,
    list_pending_migration_records,
    reject_pending_migration_record,
)
from app.database.models import PendingMigration
from app.services.skills.evolution_reviews import EvolutionReviewRecord
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)

router = APIRouter(prefix="/reviews", tags=["reviews"])

_SUMMARY_LIMIT = 160


class ReviewKind(StrEnum):
    MEMORY = "memory"
    EVOLUTION = "evolution"
    MIGRATION = "migration"


def _review_lineage_id(review_type: ReviewKind, review_id: str) -> str:
    return f"{review_type.value}:{review_id}"


class ReviewInboxItem(BaseModel):
    review_id: str
    review_type: ReviewKind
    title: str
    summary: str
    status: str
    source: str
    created_at: str
    detail: dict[str, object] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=lambda: ["approve", "reject"])


class ReviewInboxResponse(BaseModel):
    items: list[ReviewInboxItem]
    total: int
    pending_count: int
    by_type: dict[str, int] = Field(default_factory=dict)


class ReviewRejectRequest(BaseModel):
    reason: str | None = None


class ReviewActionResponse(BaseModel):
    review_id: str
    review_type: ReviewKind
    status: str


def _truncate_summary(text: str) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= _SUMMARY_LIMIT:
        return normalized
    return normalized[: _SUMMARY_LIMIT - 1].rstrip() + "…"


def _memory_review_item(record: PendingRecord) -> ReviewInboxItem:
    return ReviewInboxItem(
        review_id=record.id,
        review_type=ReviewKind.MEMORY,
        title=f"Memory review · {record.memory_type.value}",
        summary=_truncate_summary(record.content),
        status=record.status,
        source="memory.pending",
        created_at=record.created_at.isoformat(),
        detail={
            "memory_type": record.memory_type.value,
            "content": record.content,
            "extra_data": record.memory_data,
            "source_chat_id": record.source_chat_id,
            "source_message_id": record.source_message_id,
        },
    )


def _evolution_review_item(record: EvolutionReviewRecord) -> ReviewInboxItem:
    return ReviewInboxItem(
        review_id=record.id,
        review_type=ReviewKind.EVOLUTION,
        title=f"Evolution review · {record.skill_name}",
        summary=_truncate_summary(record.reason),
        status=record.status.value,
        source="evolution.pending",
        created_at=record.created_at.isoformat(),
        detail={
            "skill_id": record.skill_id,
            "skill_name": record.skill_name,
            "skill_path": record.skill_path,
            "evolution_type": record.evolution_type,
            "reason": record.reason,
            "original_content": record.original_content,
            "evolved_content": record.evolved_content,
            "confidence": record.confidence,
            "test_passed": record.test_passed,
            "approval_status": record.approval_status,
            "apply_status": record.apply_status.value,
            "apply_error": record.apply_error,
            "reason_code": record.reason_code,
            "remediation": record.remediation,
        },
    )


def _migration_review_item(record: PendingMigration) -> ReviewInboxItem:
    description = record.payload.get("description")
    return ReviewInboxItem(
        review_id=record.id,
        review_type=ReviewKind.MIGRATION,
        title=f"Migration review · {record.source}",
        summary=_truncate_summary(record.summary),
        status=record.status,
        source="migration.pending",
        created_at=record.created_at.isoformat(),
        detail={
            "source": record.source,
            "migration_type": record.migration_type,
            "summary": record.summary,
            "total_items": record.total_items,
            "item_counts": record.item_counts,
            "description": description if isinstance(description, str) else None,
        },
    )


@router.get("/inbox", response_model=ReviewInboxResponse)
async def get_review_inbox(
    limit: int = Query(50, ge=1, le=100),
    manager: MemoryManager = Depends(get_memory_manager),
) -> ReviewInboxResponse:
    memory_items: list[ReviewInboxItem] = []
    memory_total = 0

    if manager.approval_required:
        memory_records = await manager.list_pending(limit=limit)
        memory_total = await manager.count_pending()
        memory_items = [_memory_review_item(record) for record in memory_records]

    evolution_records = await list_pending_evolution_records(limit=limit)
    evolution_total = await count_pending_evolution_records()
    evolution_items = [_evolution_review_item(record) for record in evolution_records]

    migration_records = await list_pending_migration_records(limit=limit)
    migration_total = await count_pending_migration_records()
    migration_items = [_migration_review_item(record) for record in migration_records]

    items = memory_items + evolution_items + migration_items
    items.sort(key=lambda item: item.created_at, reverse=True)
    items = items[:limit]

    total = memory_total + evolution_total + migration_total
    return ReviewInboxResponse(
        items=items,
        total=total,
        pending_count=total,
        by_type={
            ReviewKind.MEMORY.value: memory_total,
            ReviewKind.EVOLUTION.value: evolution_total,
            ReviewKind.MIGRATION.value: migration_total,
        },
    )


@router.post("/{review_type}/{review_id}/approve", response_model=ReviewActionResponse)
async def approve_review_item(
    review_type: ReviewKind,
    review_id: str,
    manager: MemoryManager = Depends(get_memory_manager),
    crud_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> ReviewActionResponse:
    evolution_record: EvolutionReviewRecord | None = None
    if review_type == ReviewKind.MEMORY:
        try:
            await manager.approve(review_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    elif review_type == ReviewKind.EVOLUTION:
        evolution_record = await approve_pending_evolution_record(evolution_id=review_id)
    else:
        await approve_pending_migration_record(
            migration_id=review_id,
            manager=crud_manager,
        )

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_APPROVED,
            entity_type=ExperienceEntityType.REVIEW,
            entity_id=review_id,
            lineage_id=_review_lineage_id(review_type, review_id),
            outcome="approved",
            summary=f"Review approved for {review_type.value}:{review_id}",
            artifact_refs={"review_type": review_type.value},
            detail={"review_type": review_type.value, "review_id": review_id},
        )
    )

    return ReviewActionResponse(
        review_id=review_id,
        review_type=review_type,
        status=(
            "apply_failed"
            if review_type == ReviewKind.EVOLUTION and evolution_record.apply_status.value == "FAILED"
            else "approved"
        ),
    )


@router.post("/{review_type}/{review_id}/reject", response_model=ReviewActionResponse)
async def reject_review_item(
    review_type: ReviewKind,
    review_id: str,
    request: ReviewRejectRequest | None = None,
    manager: MemoryManager = Depends(get_memory_manager),
) -> ReviewActionResponse:
    if review_type == ReviewKind.MEMORY:
        try:
            await manager.reject(review_id)
        except Exception as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    elif review_type == ReviewKind.EVOLUTION:
        reason = request.reason if request is not None else None
        await reject_pending_evolution_record(
            evolution_id=review_id,
            reason=reason,
        )
    else:
        await reject_pending_migration_record(
            migration_id=review_id,
        )

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_REJECTED,
            entity_type=ExperienceEntityType.REVIEW,
            entity_id=review_id,
            lineage_id=_review_lineage_id(review_type, review_id),
            outcome="rejected",
            summary=f"Review rejected for {review_type.value}:{review_id}",
            artifact_refs={"review_type": review_type.value},
            detail={
                "review_type": review_type.value,
                "review_id": review_id,
                "reason": request.reason if request is not None else None,
            },
        )
    )

    return ReviewActionResponse(
        review_id=review_id,
        review_type=review_type,
        status="rejected",
    )
