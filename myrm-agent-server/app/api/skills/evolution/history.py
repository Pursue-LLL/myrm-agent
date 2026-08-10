"""
[INPUT]
- app.services.skills.evolution_reviews::EvolutionReviewRecord (POS: 以 ApprovalRecord 为唯一事实源的 evolution 审核生命周期服务)
- app.database.models.skill::ExperienceLedgerEvent (POS: 学习资产事件账本 ORM 模型)
[OUTPUT]
- Evolution history list (with quality_delta) & rollback APIs
[POS]
evolution 历史记录接口层。对外提供已处理的 evolution 历史查询（GET /history，含进化 delta）与单条回滚（POST /{id}/rollback）。
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
from app.services.skills.experience_ledger import ExperienceEventType

logger = logging.getLogger(__name__)
router = APIRouter()


def _serialize_history_record(
    record: EvolutionReviewRecord,
    quality_delta: dict[str, float | None] | None = None,
) -> dict[str, object]:
    status = (
        "rolled_back"
        if record.apply_status.value == "ROLLED_BACK"
        else record.status.value.lower()
    )
    result: dict[str, object] = {
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
    if quality_delta:
        result["quality_delta"] = quality_delta
    return result


async def _build_quality_delta_map(record_ids: list[str]) -> dict[str, dict[str, float | None]]:
    """Batch-fetch before_quality_score from ledger events for given evolution IDs."""
    if not record_ids:
        return {}

    from sqlalchemy import select

    from app.database.connection import get_session
    from app.database.models.skill import ExperienceLedgerEvent

    delta_map: dict[str, dict[str, float | None]] = {}
    async with get_session() as db:
        result = await db.execute(
            select(ExperienceLedgerEvent.entity_id, ExperienceLedgerEvent.metrics_snapshot)
            .where(
                ExperienceLedgerEvent.event_type == ExperienceEventType.EVOLUTION_APPROVED.value,
                ExperienceLedgerEvent.entity_id.in_(record_ids),
            )
        )
        for entity_id, metrics in result:
            before_score = (metrics or {}).get("before_quality_score")
            if before_score is not None:
                delta_map[entity_id] = {"before_score": float(before_score)}

    return delta_map


@router.get("/history")
async def list_evolution_history(
    limit: int = Query(20, ge=1, le=200),
) -> dict[str, list[dict[str, object]]]:
    records = await list_evolution_review_records(limit=limit, pending_only=False)
    resolved = [r for r in records if r.status.value in ("APPROVED", "REJECTED")]
    resolved = resolved[:limit]

    approved_ids = [r.id for r in resolved if r.status.value == "APPROVED"]
    delta_map = await _build_quality_delta_map(approved_ids)

    return {"items": [_serialize_history_record(r, delta_map.get(r.id)) for r in resolved]}


@router.post("/{evolution_id}/rollback")
async def rollback_pending_evolution_record(evolution_id: str) -> dict[str, object]:
    try:
        return await rollback_evolution_review_record(evolution_id)
    except EvolutionApplyError as exc:
        if "not found" not in str(exc).lower():
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/test/seed-approved", include_in_schema=False)
async def seed_approved_evolution_for_e2e(
    skill_id: str = "e2e-delta-test::content_summarizer",
    skill_name: str = "content_summarizer",
    before_quality_score: float = 0.82,
) -> dict[str, object]:
    """Local dev/E2E only: create an approved evolution with before_quality_score in ledger."""
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=403, detail="Only available in local mode")

    from app.services.skills.evolution_review.types import EvolutionGrowthStatus
    from app.services.skills.evolution_reviews import create_evolution_review_record
    from app.services.skills.experience_ledger import (
        ExperienceEntityType,
        ExperienceLedgerWrite,
        record_experience_event,
    )

    record = await create_evolution_review_record(
        agent_id="e2e-test-agent",
        chat_id=None,
        proposal_skill_id=skill_id,
        skill_name=skill_name,
        skill_path=f"/tmp/{skill_name}.md",
        evolution_type="fix",
        reason="E2E test: quality delta visualization",
        original_content="def summarize(text):\n    return text[:100]\n",
        evolved_content="def summarize(text):\n    sentences = text.split('.')\n    return '. '.join(sentences[:3]) + '.'\n",
        confidence=0.88,
        test_passed=True,
        task_context="E2E test seed",
        growth_status=EvolutionGrowthStatus.APPROVED,
        approval_status="APPROVED",
    )

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.EVOLUTION_APPROVED,
            entity_type=ExperienceEntityType.SKILL,
            entity_id=record.id,
            lineage_id=f"evolution::{record.id}",
            outcome="applied",
            summary=f"E2E seed: evolution approved for {skill_name}",
            artifact_refs={"skill_id": skill_id, "skill_name": skill_name},
            metrics_snapshot={
                "confidence": 0.88,
                "test_passed": True,
                "before_quality_score": before_quality_score,
            },
        )
    )

    return {"evolution_id": record.id, "before_quality_score": before_quality_score}
