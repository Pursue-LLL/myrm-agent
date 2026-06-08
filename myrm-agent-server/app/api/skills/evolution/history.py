"""
[INPUT]
- app.services.skills.evolution_reviews::EvolutionReviewRecord (POS: 以 ApprovalRecord 为唯一事实源的 evolution 审核生命周期服务)
[OUTPUT]
- Evolution history list & rollback APIs
[POS]
evolution 历史记录接口层。对外提供已处理的 evolution 历史查询（GET /history）与单条回滚（POST /{id}/rollback）。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

from app.services.skills.evolution_reviews import (
    EvolutionApplyError,
    EvolutionReviewRecord,
    list_evolution_review_records,
    rollback_evolution_review_record,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_history_record(record: EvolutionReviewRecord) -> dict[str, object]:
    status = (
        "rolled_back"
        if record.apply_status.value == "ROLLED_BACK"
        else record.status.value.lower()
    )
    return {
        "id": record.id,
        "skill_id": record.skill_id,
        "skill_name": record.skill_name,
        "evolution_type": record.evolution_type,
        "reason": record.reason,
        "original_content": record.original_content,
        "evolved_content": record.evolved_content,
        "confidence": record.confidence,
        "test_passed": record.test_passed,
        "status": status,
        "created_at": record.created_at.isoformat(),
        "resolved_at": record.resolved_at.isoformat() if record.resolved_at else None,
    }


@router.get("/history")
async def list_evolution_history(
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, list[dict[str, object]]]:
    records = await list_evolution_review_records(limit=limit, pending_only=False)
    resolved = [r for r in records if r.status.value in ("APPROVED", "REJECTED")]
    return {"items": [_serialize_history_record(r) for r in resolved[:limit]]}


@router.post("/{evolution_id}/rollback")
async def rollback_pending_evolution_record(evolution_id: str) -> dict[str, object]:
    try:
        return await rollback_evolution_review_record(evolution_id)
    except EvolutionApplyError as exc:
        if "not found" not in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc
