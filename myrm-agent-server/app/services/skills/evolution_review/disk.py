"""
[INPUT]
- .types::EvolutionApprovalPayload (POS: Evolution 审核域类型)
- .disk_content::apply_content_update, rollback_content_update (POS: Evolution 全量内容更新落盘与回滚)
- .persistence::persist_approval_payload (POS: Evolution 审核 ApprovalRecord 持久化读写)
- ..experience_ledger::record_experience_event (POS: 学习资产事件账本)
- app.adapters.skill_optimization.quality_repo::QualityRepository (POS: 质量数据 CRUD)
[OUTPUT]
- Description/content apply orchestration, shadow apply, approval apply pipeline
- _fetch_before_quality_score: 进化前质量分数获取
[POS]
Evolution 落盘编排（description / shadow / approval 成功路径）。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timezone

from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EnvironmentFingerprint,
    EvolutionType,
    SkillLineage,
)
from myrm_agent_harness.eval.manifest_prediction import (
    MetricPrediction,
    PredictionDirection,
    evaluate_manifest_attribution,
)

from app.core.skills.config_version import bump_skill_config_version
from app.database.models import ApprovalRecord

from ..experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)
from .disk_content import (
    apply_content_update,
    rollback_content_update,
)
from .persistence import persist_approval_payload
from .types import (
    EvolutionApplyError,
    EvolutionApplyStatus,
    EvolutionApprovalPayload,
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    apply_failure_remediation,
    approval_payload,
    approval_to_evolution_review_record,
    evolution_lineage_id,
)

logger = logging.getLogger(__name__)


def get_skill_store() -> SkillStore:
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    return get_evolution_skill_store()


async def enqueue_cognitive_subsumption(payload: EvolutionApprovalPayload) -> None:
    from myrm_agent_harness.agent.background_worker.registry import (
        get_idle_task_registry,
    )

    from app.config.settings import settings

    registry = get_idle_task_registry(workspace_root=settings.database.state_dir)
    await registry.enqueue(
        session_id="global",
        task_type="cognitive_subsumption",
        payload={
            "new_knowledge": payload.evolved_content,
            "skill_id": payload.skill_id,
        },
    )


async def apply_to_disk_and_store(
    payload: EvolutionApprovalPayload,
    agent_id: str | None = None,
    *,
    apply_mode: str = "immediate",
) -> None:
    store = get_skill_store()
    if payload.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION.value:
        await apply_description_update(payload, store, agent_id)
    elif apply_mode == "shadow":
        await apply_content_shadow(payload)
    else:
        await apply_content_update(payload, store, agent_id)

    if apply_mode != "shadow":
        try:
            await enqueue_cognitive_subsumption(payload)
        except Exception as exc:
            logger.warning("Failed to enqueue cognitive_subsumption task: %s", exc)

        bump_skill_config_version()


async def apply_description_update(
    payload: EvolutionApprovalPayload,
    store: SkillStore,
    agent_id: str | None = None,
) -> None:
    existing = store.get_skill(payload.skill_id)
    if existing is None:
        raise EvolutionApplyError(f"Cannot apply description update: skill '{payload.skill_id}' not found in store.")

    existing.description = payload.evolved_content
    existing.lineage = SkillLineage(
        parent_id=payload.skill_id,
        evolution_type=EvolutionType.OPTIMIZE_DESCRIPTION,
        change_summary=payload.reason,
        created_at=datetime.now(),
        created_by="evolution_engine",
    )
    if agent_id:
        if existing.environment is None:
            existing.environment = EnvironmentFingerprint()
        existing.environment.custom_tags["scope_agent_id"] = agent_id

    await store.save_skill(existing)


async def mark_apply_failure(
    record: ApprovalRecord,
    payload: EvolutionApprovalPayload,
    error_message: str,
    *,
    auto_approved: bool,
) -> ApprovalRecord:
    payload.growth_status = EvolutionGrowthStatus.APPLY_FAILED
    payload.apply_status = EvolutionApplyStatus.FAILED
    payload.apply_error = error_message
    payload.reason_code = "apply_failed"
    payload.remediation = apply_failure_remediation(payload.skill_name)
    approval_status = "APPROVED"
    if auto_approved:
        approval_status = "PENDING"
    updated = await persist_approval_payload(
        record.id,
        approval_status=approval_status,
        payload=payload,
        resolved_at=(datetime.now(timezone.utc) if approval_status == "APPROVED" else None),
    )
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.EVOLUTION_APPLY_FAILED,
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=record.id,
            lineage_id=evolution_lineage_id(record.id),
            outcome="apply_failed",
            summary=payload.reason,
            artifact_refs={
                "skill_id": payload.skill_id,
                "skill_name": payload.skill_name,
            },
            metrics_snapshot={
                "confidence": payload.confidence,
                "test_passed": payload.test_passed,
            },
            detail={
                "evolution_type": payload.evolution_type,
                "apply_status": payload.apply_status.value,
                "apply_error": payload.apply_error,
                "reason_code": payload.reason_code,
                "remediation": payload.remediation,
            },
        )
    )
    return updated


async def apply_content_shadow(payload: EvolutionApprovalPayload) -> None:
    from app.services.skill_optimization.bootstrap import (
        get_skill_optimization_storage as get_storage,
    )
    from app.services.skill_optimization.skill_version_sync import start_shadow_ab_test

    storage = get_storage()
    await start_shadow_ab_test(storage, payload.skill_id, payload.evolved_content)


async def _fetch_before_quality_score(skill_id: str) -> float | None:
    """Retrieve the latest quality score before evolution is applied."""
    from app.adapters.skill_optimization.quality_repo import QualityRepository
    from app.database.connection import get_session

    try:
        async with get_session() as db:
            repo = QualityRepository(db)
            latest = await repo.get_latest_quality(skill_id)
            return latest.overall_score if latest else None
    except Exception as exc:
        logger.debug("Could not fetch before_quality_score for %s: %s", skill_id, exc)
        return None


def _attribute_manifest_after_apply(
    payload: EvolutionApprovalPayload,
) -> dict[str, object] | None:
    """Attribute actual static-assertion metrics back to the change prediction manifest.

    Uses the manifest snapshot persisted at proposal creation (payload.change_manifest)
    and the eval_cases snapshot persisted alongside it (payload.eval_cases), so the
    prediction baseline cannot drift after the fact. The applied content's actual
    pass rate is computed with the same deterministic zero-LLM assertion engine.
    Returns None when no manifest exists (no eval_cases / description-only evolution).
    """
    manifest_dict = payload.change_manifest
    if not isinstance(manifest_dict, dict) or not manifest_dict.get("predictions"):
        return None

    from myrm_agent_harness.agent.skills.evolution.core.eval_regression import (
        evaluate_content_assertions,
    )
    from myrm_agent_harness.eval.manifest_prediction import ChangePredictionManifest

    try:
        manifest = ChangePredictionManifest(
            manifest_id=str(manifest_dict.get("manifest_id", "")),
            target_component=str(manifest_dict.get("target_component", "")),
            rationale=str(manifest_dict.get("rationale", "")),
            created_at=manifest_dict.get("created_at"),
            rollback_patch=manifest_dict.get("rollback_patch"),
            predictions=[],
        )
        for pred in manifest_dict["predictions"]:
            if not isinstance(pred, dict):
                continue
            manifest.predictions.append(
                MetricPrediction(
                    metric_name=str(pred.get("metric_name", "")),
                    direction=PredictionDirection(str(pred.get("direction", "neutral"))),
                    baseline_value=float(pred.get("baseline_value", 0.0)),
                    target_value=float(pred.get("target_value", 0.0)),
                    tolerance=float(pred.get("tolerance", 0.02)),
                )
            )

        actual_metrics = {"pass_rate": evaluate_content_assertions(payload.eval_cases, payload.evolved_content)}
        result = evaluate_manifest_attribution(manifest, actual_metrics)
        return result.to_dict()
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "Change manifest attribution failed for skill '%s': %s",
            payload.skill_id,
            exc,
        )
        return None


async def apply_approval_record(
    record: ApprovalRecord,
    *,
    auto_approved: bool,
    apply_mode: str = "immediate",
) -> EvolutionReviewRecord:
    payload = approval_payload(record)
    if payload is None:
        raise EvolutionApplyError("Evolution approval payload is invalid.")

    before_quality_score = await _fetch_before_quality_score(payload.skill_id)

    try:
        await apply_to_disk_and_store(payload, agent_id=record.agent_id, apply_mode=apply_mode)
    except Exception as exc:
        await mark_apply_failure(record, payload, str(exc), auto_approved=auto_approved)
        raise EvolutionApplyError(str(exc)) from exc

    payload.apply_status = EvolutionApplyStatus.APPLIED
    payload.apply_error = None
    payload.remediation = None
    payload.reason_code = None if payload.growth_status == EvolutionGrowthStatus.APPROVED else payload.reason_code
    payload.growth_status = EvolutionGrowthStatus.APPROVED

    attribution = _attribute_manifest_after_apply(payload)
    if attribution is not None:
        payload.attribution_result = attribution

    updated = await persist_approval_payload(
        record.id,
        approval_status="APPROVED",
        payload=payload,
        resolved_at=datetime.now(timezone.utc),
    )

    metrics: dict[str, object] = {
        "confidence": payload.confidence,
        "test_passed": payload.test_passed,
    }
    if before_quality_score is not None:
        metrics["before_quality_score"] = before_quality_score

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.EVOLUTION_APPROVED,
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=record.id,
            lineage_id=evolution_lineage_id(record.id),
            outcome="approved",
            summary=payload.reason,
            artifact_refs={
                "skill_id": payload.skill_id,
                "skill_name": payload.skill_name,
            },
            metrics_snapshot=metrics,
            detail={
                "evolution_type": payload.evolution_type,
                "skill_path": payload.skill_path,
                "apply_status": payload.apply_status.value,
                "attribution_verdict": (
                    (payload.attribution_result or {}).get("overall_verdict")
                    if isinstance(payload.attribution_result, dict)
                    else None
                ),
            },
        )
    )
    review_record = approval_to_evolution_review_record(updated)
    if review_record is None:
        raise EvolutionApplyError(f"Failed to normalize approved evolution record: {updated.id}")
    return review_record


async def rollback_description_update(payload: EvolutionApprovalPayload, store: SkillStore) -> None:
    existing = store.get_skill(payload.skill_id)
    if existing is None:
        raise EvolutionApplyError(f"Cannot rollback description update: skill '{payload.skill_id}' not found.")
    existing.description = payload.original_content
    existing.lineage = SkillLineage(
        evolution_type=EvolutionType.OPTIMIZE_DESCRIPTION,
        version=1,
        parent_id=None,
        change_summary="Rolled back",
        created_at=datetime.now(UTC),
        created_by="user",
    )
    await store.save_skill(existing)


__all__ = [
    "apply_approval_record",
    "apply_to_disk_and_store",
    "get_skill_store",
    "rollback_content_update",
    "rollback_description_update",
]
