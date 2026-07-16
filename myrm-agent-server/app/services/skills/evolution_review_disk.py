"""
[INPUT]
- app.services.skills.evolution_review_types::EvolutionApprovalPayload
[OUTPUT]
- Description/content apply orchestration, shadow apply, approval apply pipeline
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

from app.core.skills.config_version import bump_skill_config_version
from app.database.models import ApprovalRecord
from app.services.skills.evolution_review_disk_content import (
    apply_content_update,
    rollback_content_update,
)
from app.services.skills.evolution_review_persistence import persist_approval_payload
from app.services.skills.evolution_review_types import (
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
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
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
    try:
        if payload.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION.value:
            await apply_description_update(payload, store, agent_id)
        elif apply_mode == "shadow":
            await apply_content_shadow(payload)
        else:
            await apply_content_update(payload, store, agent_id)
    finally:
        store.close()

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
    from app.services.skill_optimization.bootstrap import get_skill_optimization_storage as get_storage
    from app.services.skill_optimization.skill_version_sync import start_shadow_ab_test

    storage = get_storage()
    await start_shadow_ab_test(storage, payload.skill_id, payload.evolved_content)


async def apply_approval_record(
    record: ApprovalRecord,
    *,
    auto_approved: bool,
    apply_mode: str = "immediate",
) -> EvolutionReviewRecord:
    payload = approval_payload(record)
    if payload is None:
        raise EvolutionApplyError("Evolution approval payload is invalid.")

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

    updated = await persist_approval_payload(
        record.id,
        approval_status="APPROVED",
        payload=payload,
        resolved_at=datetime.now(timezone.utc),
    )
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
            metrics_snapshot={
                "confidence": payload.confidence,
                "test_passed": payload.test_passed,
            },
            detail={
                "evolution_type": payload.evolution_type,
                "skill_path": payload.skill_path,
                "apply_status": payload.apply_status.value,
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
