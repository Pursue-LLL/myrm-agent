"""
[INPUT]
- app.services.approvals.registry::ApprovalRegistry
- app.services.skills.evolution_review_disk
[OUTPUT]
- approve/reject/revise/rollback evolution review records
[POS]
Evolution 审核写操作：审批决议、修订提案、回滚已落地变更。
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType

from app.core.skills.config_version import bump_skill_config_version
from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.evolution_review_disk import (
    apply_approval_record,
    get_skill_store,
    rollback_content_update,
    rollback_description_update,
)
from app.services.skills.evolution_review_persistence import load_approval_record, persist_approval_payload
from app.services.skills.evolution_review_types import (
    MAX_SKILL_CONTENT_CHARS,
    EvolutionApplyError,
    EvolutionApplyStatus,
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
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


async def approve_evolution_review_record(
    evolution_id: str,
    *,
    auto_approved: bool = False,
    apply_mode: str = "immediate",
) -> EvolutionReviewRecord:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")

    current = approval_to_evolution_review_record(approval_record)
    if current is None:
        raise EvolutionApplyError(f"Invalid evolution approval record: {evolution_id}")

    if current.status in {
        EvolutionGrowthStatus.REJECTED,
        EvolutionGrowthStatus.FAILED_SCAN,
        EvolutionGrowthStatus.BLOCKED_LOCKED,
    }:
        raise EvolutionApplyError("Blocked evolution cannot be approved.")

    record = approval_record
    if approval_record.status != "APPROVED":
        resolved = await ApprovalRegistry.resolve_approval(
            approval_id=evolution_id,
            decision="approve",
            edited_payload={"growth_status": EvolutionGrowthStatus.APPROVED.value},
        )
        if resolved is None:
            raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")
        record = resolved

    return await apply_approval_record(record, auto_approved=auto_approved, apply_mode=apply_mode)


async def reject_evolution_review_record(
    evolution_id: str,
    *,
    reason: str | None = None,
) -> EvolutionReviewRecord:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")

    payload = approval_payload(approval_record)
    if payload is None:
        raise EvolutionApplyError(f"Invalid evolution approval record: {evolution_id}")

    payload.growth_status = EvolutionGrowthStatus.REJECTED
    payload.reject_reason = reason
    payload.reason_code = "rejected"
    if reason and reason.strip():
        payload.remediation = reason.strip()

    if approval_record.status != "REJECTED":
        resolved = await ApprovalRegistry.resolve_approval(
            approval_id=evolution_id,
            decision="deny",
            edited_payload=payload.model_dump(mode="json"),
        )
        if resolved is None:
            raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")
        approval_record = resolved
    else:
        approval_record = await persist_approval_payload(
            evolution_id,
            approval_status="REJECTED",
            payload=payload,
            resolved_at=datetime.now(timezone.utc),
        )

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.EVOLUTION_REJECTED,
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=approval_record.id,
            lineage_id=evolution_lineage_id(approval_record.id),
            outcome="rejected",
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
                "reject_reason": reason,
                "reason_code": payload.reason_code,
                "remediation": payload.remediation,
            },
        )
    )

    if reason and reason.strip():
        store = get_skill_store()
        try:
            await store.add_evolution_constraint(payload.skill_id, reason.strip())
        finally:
            store.close()

    review_record = approval_to_evolution_review_record(approval_record)
    if review_record is None:
        raise EvolutionApplyError(f"Failed to normalize rejected evolution record: {approval_record.id}")
    return review_record


async def revise_evolution_review_record(
    evolution_id: str,
    *,
    evolved_content: str,
) -> EvolutionReviewRecord:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")

    payload = approval_payload(approval_record)
    if payload is None:
        raise EvolutionApplyError(f"Invalid evolution approval record: {evolution_id}")

    if payload.growth_status not in {
        EvolutionGrowthStatus.PENDING_REVIEW,
        EvolutionGrowthStatus.APPLY_FAILED,
    }:
        raise EvolutionApplyError(
            f"Only pending or apply-failed proposals can be revised. Current status: {payload.growth_status.value}"
        )

    if not evolved_content or not evolved_content.strip():
        raise EvolutionApplyError("Revised content cannot be empty.")

    if len(evolved_content) > MAX_SKILL_CONTENT_CHARS:
        raise EvolutionApplyError(
            f"Revised content too large ({len(evolved_content)} chars, max {MAX_SKILL_CONTENT_CHARS})."
        )

    scan_passed = True
    try:
        from myrm_agent_harness.backends.skills.scanning.scanner import scan_skill_content

        scan_result = scan_skill_content(payload.skill_name, evolved_content)
        scan_passed = scan_result.is_clean
    except Exception as exc:
        logger.warning("Security scan failed during revision for %s: %s", evolution_id, exc)

    payload.evolved_content = evolved_content
    payload.test_passed = scan_passed
    if not scan_passed:
        payload.growth_status = EvolutionGrowthStatus.FAILED_SCAN
        payload.reason_code = "revised_failed_scan"
        payload.remediation = "Revised content failed security scan. Please fix the flagged issues."
    else:
        payload.growth_status = EvolutionGrowthStatus.PENDING_REVIEW
        payload.apply_status = EvolutionApplyStatus.NOT_APPLIED
        payload.apply_error = None
        payload.reason_code = "revised"
        payload.remediation = None

    updated = await persist_approval_payload(
        evolution_id,
        payload=payload,
    )

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.EVOLUTION_PENDING,
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=evolution_id,
            lineage_id=evolution_lineage_id(evolution_id),
            outcome="revised",
            summary=f"Human revised evolution proposal for {payload.skill_name}",
            artifact_refs={
                "skill_id": payload.skill_id,
                "skill_name": payload.skill_name,
            },
            metrics_snapshot={
                "confidence": payload.confidence,
                "test_passed": scan_passed,
            },
            detail={
                "evolution_type": payload.evolution_type,
                "revision_scan_passed": scan_passed,
            },
        )
    )

    review_record = approval_to_evolution_review_record(updated)
    if review_record is None:
        raise EvolutionApplyError(f"Failed to normalize revised evolution record: {updated.id}")
    return review_record


async def rollback_evolution_review_record(evolution_id: str) -> dict[str, object]:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")

    payload = approval_payload(approval_record)
    if payload is None:
        raise EvolutionApplyError(f"Invalid evolution approval record: {evolution_id}")
    if payload.apply_status != EvolutionApplyStatus.APPLIED:
        raise EvolutionApplyError("Only applied evolutions can be rolled back.")

    store = get_skill_store()
    try:
        if payload.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION.value:
            await rollback_description_update(payload, store)
        else:
            await rollback_content_update(payload, store)
    finally:
        store.close()

    payload.apply_status = EvolutionApplyStatus.ROLLED_BACK
    payload.apply_error = None
    payload.reason_code = "rolled_back"
    payload.remediation = "Review the original content before re-applying this evolution."
    await persist_approval_payload(
        evolution_id,
        approval_status="APPROVED",
        payload=payload,
        resolved_at=approval_record.resolved_at,
    )

    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=ExperienceEventType.EVOLUTION_ROLLED_BACK,
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=approval_record.id,
            lineage_id=evolution_lineage_id(approval_record.id),
            outcome="rolled_back",
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

    bump_skill_config_version()
    return {"status": "rolled_back", "evolution_id": evolution_id}
