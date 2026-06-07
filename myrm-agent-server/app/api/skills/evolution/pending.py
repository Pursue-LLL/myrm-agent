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


class PendingEvolutionResponse(BaseModel):
    id: str
    skill_id: str
    skill_name: str
    evolution_type: str
    reason: str
    original_content: str
    evolved_content: str
    confidence: float
    test_passed: bool
    status: str
    approval_status: str
    apply_status: str
    apply_error: str | None = None
    reason_code: str | None = None
    remediation: str | None = None
    trajectory: str | None = None
    created_at: str


class RejectEvolutionRequest(BaseModel):
    reason: str | None = None


class ApproveEvolutionRequest(BaseModel):
    apply_mode: str = "immediate"


class ReviseEvolutionRequest(BaseModel):
    evolved_content: str


def _response_from_record(record: EvolutionReviewRecord) -> PendingEvolutionResponse:
    return PendingEvolutionResponse(
        id=record.id,
        skill_id=record.skill_id,
        skill_name=record.skill_name,
        evolution_type=record.evolution_type,
        reason=record.reason,
        original_content=record.original_content,
        evolved_content=record.evolved_content,
        confidence=record.confidence,
        test_passed=record.test_passed,
        status=record.status.value,
        approval_status=record.approval_status,
        apply_status=record.apply_status.value,
        apply_error=record.apply_error,
        reason_code=record.reason_code,
        remediation=record.remediation,
        trajectory=record.trajectory,
        created_at=record.created_at.isoformat(),
    )


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
) -> dict[str, list[PendingEvolutionResponse]]:
    records = await list_pending_evolution_records(limit=limit)
    return {"items": [_response_from_record(record) for record in records]}


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
