"""
[INPUT]
- app.services.skills.evolution_reviews::EvolutionReviewRecord (POS: 以 ApprovalRecord 为唯一事实源的 evolution 审核生命周期服务)
- app.services.skills.experience_ledger::record_experience_event (POS: 学习资产事件账本服务)
[OUTPUT]
- Pending evolution review APIs
[POS]
evolution 审核接口层。对外提供 pending 列表、approve、reject、revise，以 ApprovalRecord 为唯一事实源。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.services.skills.evolution_reviews import (
    EvolutionApplyError,
    EvolutionReviewRecord,
    approve_evolution_review_record,
    count_evolution_review_records,
    evolution_lineage_id,
    get_evolution_review_record,
    list_evolution_review_records,
    reject_evolution_review_record,
    revise_evolution_review_record,
)
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)

router = APIRouter()
logger = logging.getLogger(__name__)


class PendingEvolutionSummaryResponse(BaseModel):
    id: str
    skill_id: str
    skill_name: str
    evolution_type: str
    reason: str
    confidence: float
    test_passed: bool
    status: str
    approval_status: str
    apply_status: str
    apply_error: str | None = None
    reason_code: str | None = None
    remediation: str | None = None
    has_diff: bool = False
    has_trajectory: bool = False
    chat_id: str | None = None
    created_at: str


class PendingEvolutionDetailResponse(PendingEvolutionSummaryResponse):
    original_content: str
    evolved_content: str
    trajectory: str | None = None


class PendingEvolutionResponse(PendingEvolutionDetailResponse):
    """Backward-compatible alias for tests expecting full bodies in list responses."""


def _summary_from_record(record: EvolutionReviewRecord) -> PendingEvolutionSummaryResponse:
    return PendingEvolutionSummaryResponse(
        id=record.id,
        skill_id=record.skill_id,
        skill_name=record.skill_name,
        evolution_type=record.evolution_type,
        reason=record.reason,
        confidence=record.confidence,
        test_passed=record.test_passed,
        status=record.status.value,
        approval_status=record.approval_status,
        apply_status=record.apply_status.value,
        apply_error=record.apply_error,
        reason_code=record.reason_code,
        remediation=record.remediation,
        has_diff=bool(record.original_content or record.evolved_content),
        has_trajectory=bool(record.trajectory),
        chat_id=record.chat_id,
        created_at=record.created_at.isoformat(),
    )


def _detail_from_record(record: EvolutionReviewRecord) -> PendingEvolutionDetailResponse:
    summary = _summary_from_record(record)
    return PendingEvolutionDetailResponse(
        **summary.model_dump(),
        original_content=record.original_content,
        evolved_content=record.evolved_content,
        trajectory=record.trajectory,
    )


def _response_from_record(record: EvolutionReviewRecord) -> PendingEvolutionResponse:
    return PendingEvolutionResponse(**_detail_from_record(record).model_dump())


class RejectEvolutionRequest(BaseModel):
    reason: str | None = None


class ApproveEvolutionRequest(BaseModel):
    apply_mode: str = "immediate"


class ReviseEvolutionRequest(BaseModel):
    evolved_content: str


async def list_pending_evolution_records(limit: int) -> list[EvolutionReviewRecord]:
    return await list_evolution_review_records(limit=limit, pending_only=True)


async def count_pending_evolution_records() -> int:
    return await count_evolution_review_records(pending_only=True)


async def approve_pending_evolution_record(
    evolution_id: str,
    *,
    apply_mode: str = "immediate",
) -> EvolutionReviewRecord:
    try:
        return await approve_evolution_review_record(evolution_id, apply_mode=apply_mode)
    except EvolutionApplyError as exc:
        if "not found" not in str(exc).lower():
            latest_record = await get_evolution_review_record(evolution_id)
            if latest_record is not None and latest_record.apply_status.value == "FAILED":
                return latest_record
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc


async def reject_pending_evolution_record(
    evolution_id: str,
    reason: str | None = None,
) -> EvolutionReviewRecord:
    try:
        return await reject_evolution_review_record(evolution_id, reason=reason)
    except EvolutionApplyError as exc:
        if "not found" not in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/pending")
async def get_pending_evolutions(
    limit: int = Query(50, ge=1, le=100),
) -> dict[str, list[PendingEvolutionSummaryResponse]]:
    records = await list_pending_evolution_records(limit=limit)
    return {"items": [_summary_from_record(record) for record in records]}


@router.get("/pending/{evolution_id}")
async def get_pending_evolution(evolution_id: str) -> PendingEvolutionDetailResponse:
    record = await get_evolution_review_record(evolution_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"Pending evolution not found: {evolution_id}")
    return _detail_from_record(record)


@router.post("/pending/{evolution_id}/approve")
async def approve_pending_evolution(
    evolution_id: str,
    request: ApproveEvolutionRequest | None = None,
) -> dict[str, str | None]:
    apply_mode = request.apply_mode if request is not None else "immediate"
    if apply_mode not in {"immediate", "shadow"}:
        raise HTTPException(status_code=400, detail="apply_mode must be 'immediate' or 'shadow'")
    record = await approve_pending_evolution_record(evolution_id=evolution_id, apply_mode=apply_mode)
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_APPROVED,
            entity_type=ExperienceEntityType.REVIEW,
            entity_id=evolution_id,
            lineage_id=evolution_lineage_id(evolution_id),
            outcome="approved",
            summary=f"Review approved for evolution:{evolution_id}",
            artifact_refs={"review_type": "evolution", "skill_id": record.skill_id},
            detail={
                "review_type": "evolution",
                "review_id": evolution_id,
                "apply_status": record.apply_status.value,
                "apply_error": record.apply_error,
                "reason_code": record.reason_code,
                "remediation": record.remediation,
            },
        )
    )
    return {
        "status": ("apply_failed" if record.apply_status.value == "FAILED" else "approved"),
        "skill_id": record.skill_id,
        "apply_status": record.apply_status.value,
        "apply_error": record.apply_error,
        "remediation": record.remediation,
    }


@router.post("/pending/{evolution_id}/reject")
async def reject_pending_evolution(
    evolution_id: str,
    request: RejectEvolutionRequest | None = None,
) -> dict[str, str | None]:
    record = await reject_pending_evolution_record(
        evolution_id=evolution_id,
        reason=request.reason if request is not None else None,
    )
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.REVIEW_REJECTED,
            entity_type=ExperienceEntityType.REVIEW,
            entity_id=evolution_id,
            lineage_id=evolution_lineage_id(evolution_id),
            outcome="rejected",
            summary=f"Review rejected for evolution:{evolution_id}",
            artifact_refs={"review_type": "evolution", "skill_id": record.skill_id},
            detail={
                "review_type": "evolution",
                "review_id": evolution_id,
                "reason": request.reason if request is not None else None,
                "reason_code": record.reason_code,
                "remediation": record.remediation,
            },
        )
    )
    return {
        "status": "rejected",
        "skill_id": record.skill_id,
        "apply_status": record.apply_status.value,
        "remediation": record.remediation,
    }


@router.patch("/pending/{evolution_id}/revise")
async def revise_pending_evolution(
    evolution_id: str,
    request: ReviseEvolutionRequest,
) -> dict[str, str | bool | None]:
    """Revise the proposed content of a pending evolution before approval.

    Allows the user to edit the evolved_content in-place, then re-validates
    via security scanning. The record stays in PENDING_REVIEW state (or moves
    to FAILED_SCAN if the revised content fails scanning).
    """
    try:
        record = await revise_evolution_review_record(
            evolution_id, evolved_content=request.evolved_content
        )
    except EvolutionApplyError as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "status": record.status.value,
        "skill_id": record.skill_id,
        "test_passed": record.test_passed,
        "reason_code": record.reason_code,
        "remediation": record.remediation,
    }
