"""
[INPUT]
- app.services.approvals.registry::ApprovalRegistry
- .disk (POS: Evolution 落盘编排)
- .persistence::load_approval_record, persist_approval_payload (POS: Evolution 审核 ApprovalRecord 持久化读写)
- .types::EvolutionApprovalPayload (POS: Evolution 审核域类型)
- ..experience_ledger::record_experience_event (POS: 学习资产事件账本)
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

from ..experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)
from .disk import (
    apply_approval_record,
    get_skill_store,
    rollback_content_update,
    rollback_description_update,
)
from .persistence import load_approval_record, persist_approval_payload
from .types import (
    MAX_SKILL_CONTENT_CHARS,
    EvolutionApplyError,
    EvolutionApplyStatus,
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    approval_payload,
    approval_to_evolution_review_record,
    evolution_lineage_id,
)

logger = logging.getLogger(__name__)


def _rebuild_manifest_after_revision(
    payload: EvolutionApprovalPayload, revised_content: str
) -> dict[str, object] | None:
    """Recompute the manifest's target pass rate after a human revision.

    Keeps the falsifiable prediction consistent with the content that will
    actually be applied (the original manifest targeted the pre-revision
    content and would be stale). Baseline (original content) and eval_cases
    snapshot are preserved unchanged. Returns None when no manifest exists.
    """
    manifest_dict = payload.change_manifest
    if not isinstance(manifest_dict, dict) or not manifest_dict.get("predictions"):
        return None

    from myrm_agent_harness.agent.skills.evolution.core.eval_regression import (
        evaluate_content_assertions,
    )
    from myrm_agent_harness.eval.manifest_prediction import MetricPrediction

    try:
        rebuilt: dict[str, object] = dict(manifest_dict)
        new_predictions: list[dict[str, object]] = []
        for pred in manifest_dict["predictions"]:
            if not isinstance(pred, dict) or pred.get("metric_name") != "pass_rate":
                new_predictions.append(pred)
                continue
            updated = dict(pred)
            updated["target_value"] = evaluate_content_assertions(
                payload.eval_cases, revised_content
            )
            new_predictions.append(updated)
        rebuilt["predictions"] = new_predictions
        return rebuilt
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "Change manifest re-prediction failed for skill '%s': %s",
            payload.skill_id,
            exc,
        )
        return None


def _rebuild_manifest_after_revision(
    payload: EvolutionApprovalPayload, revised_content: str
) -> dict[str, object] | None:
    """Rebuild the change manifest predictions after a human revision.

    The revision replaces the previously predicted content, so stale targets would
    make the post-apply attribution meaningless. Baseline (original content) and the
    eval_cases snapshot stay fixed; only the predicted target is recomputed against
    the revised content with the same deterministic assertion engine.
    """
    manifest_dict = payload.change_manifest
    if not isinstance(manifest_dict, dict) or not manifest_dict.get("predictions"):
        return None

    from myrm_agent_harness.agent.skills.evolution.core.eval_regression import (
        evaluate_content_assertions,
    )
    from myrm_agent_harness.eval.manifest_prediction import PredictionDirection

    try:
        for pred in manifest_dict["predictions"]:
            if not isinstance(pred, dict) or pred.get("metric_name") != "pass_rate":
                continue
            baseline = float(pred.get("baseline_value", 0.0))
            revised_rate = evaluate_content_assertions(
                payload.eval_cases, revised_content
            )
            pred["target_value"] = max(
                evaluate_content_assertions(payload.eval_cases, revised_content),
                baseline,
            )
            pred["direction"] = PredictionDirection.INCREASE.value
            break
        else:
            return None
        return manifest_dict
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "Manifest prediction rebuild failed for skill '%s': %s",
            payload.skill_id,
            exc,
        )
        return None


def _rebuild_manifest_after_revision(
    payload: EvolutionApprovalPayload, revised_content: str
) -> dict[str, object] | None:
    """Recompute the prediction manifest after a manual revision.

    The original manifest's target was computed against the pre-revision
    proposed content; once the user edits that content the prediction would go
    stale, so baseline/target are recomputed from the eval_cases snapshot.
    Returns None when no manifest or no eval_cases exist (nothing to predict).
    """
    manifest_dict = payload.change_manifest
    if (
        not isinstance(manifest_dict, dict)
        or not manifest_dict.get("predictions")
        or not payload.eval_cases
    ):
        return None

    from myrm_agent_harness.agent.skills.evolution.core.eval_regression import (
        evaluate_content_assertions,
    )
    from myrm_agent_harness.eval.manifest_prediction import (
        ChangePredictionManifest,
        MetricPrediction,
        PredictionDirection,
    )

    try:
        original_pred = next(
            p
            for p in manifest_dict["predictions"]
            if p.get("metric_name") == "pass_rate"
        )
    except StopIteration:
        return None

    baseline = float(original_pred["baseline_value"])
    target_pass_rate = evaluate_content_assertions(payload.eval_cases, revised_content)
    revised_pred = MetricPrediction(
        metric_name="pass_rate",
        direction=PredictionDirection.INCREASE,
        baseline_value=baseline,
        target_value=max(target_pass_rate, baseline),
        tolerance=float(original_pred.get("tolerance", 0.05)),
    )

    manifest = ChangePredictionManifest(
        manifest_id=str(manifest_dict.get("manifest_id", "")),
        target_component=str(manifest_dict.get("target_component", "")),
        rationale=f"Revised: {manifest_dict.get('rationale', '')}".strip(),
        rollback_patch=manifest_dict.get("rollback_patch"),
        created_at=manifest_dict.get("created_at"),
        predictions=[revised_pred],
    )
    return manifest.to_dict()


async def approve_evolution_review_record(
    evolution_id: str,
    *,
    auto_approved: bool = False,
    apply_mode: str = "immediate",
) -> EvolutionReviewRecord:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(
            f"Evolution approval record not found: {evolution_id}"
        )

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
            raise EvolutionApplyError(
                f"Evolution approval record not found: {evolution_id}"
            )
        record = resolved

    return await apply_approval_record(
        record, auto_approved=auto_approved, apply_mode=apply_mode
    )


async def reject_evolution_review_record(
    evolution_id: str,
    *,
    reason: str | None = None,
) -> EvolutionReviewRecord:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(
            f"Evolution approval record not found: {evolution_id}"
        )

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
            raise EvolutionApplyError(
                f"Evolution approval record not found: {evolution_id}"
            )
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
        await store.add_evolution_constraint(payload.skill_id, reason.strip())

    review_record = approval_to_evolution_review_record(approval_record)
    if review_record is None:
        raise EvolutionApplyError(
            f"Failed to normalize rejected evolution record: {approval_record.id}"
        )
    return review_record


async def revise_evolution_review_record(
    evolution_id: str,
    *,
    evolved_content: str,
) -> EvolutionReviewRecord:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(
            f"Evolution approval record not found: {evolution_id}"
        )

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
        from myrm_agent_harness.backends.skills.scanning.scanner import (
            scan_skill_content,
        )

        scan_result = scan_skill_content(payload.skill_name, evolved_content)
        scan_passed = scan_result.is_clean
    except Exception as exc:
        logger.warning(
            "Security scan failed during revision for %s: %s", evolution_id, exc
        )

    payload.evolved_content = evolved_content
    payload.test_passed = scan_passed
    if not scan_passed:
        payload.growth_status = EvolutionGrowthStatus.FAILED_SCAN
        payload.reason_code = "revised_failed_scan"
        payload.remediation = (
            "Revised content failed security scan. Please fix the flagged issues."
        )
    else:
        payload.growth_status = EvolutionGrowthStatus.PENDING_REVIEW
        payload.apply_status = EvolutionApplyStatus.NOT_APPLIED
        payload.apply_error = None
        payload.reason_code = "revised"
        payload.remediation = None
        payload.change_manifest = _rebuild_manifest_after_revision(
            payload, evolved_content
        )

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
        raise EvolutionApplyError(
            f"Failed to normalize revised evolution record: {updated.id}"
        )
    return review_record


async def rollback_evolution_review_record(evolution_id: str) -> dict[str, object]:
    approval_record = await load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(
            f"Evolution approval record not found: {evolution_id}"
        )

    payload = approval_payload(approval_record)
    if payload is None:
        raise EvolutionApplyError(f"Invalid evolution approval record: {evolution_id}")
    if payload.apply_status != EvolutionApplyStatus.APPLIED:
        raise EvolutionApplyError("Only applied evolutions can be rolled back.")

    store = get_skill_store()
    if payload.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION.value:
        await rollback_description_update(payload, store)
    else:
        await rollback_content_update(payload, store)

    payload.apply_status = EvolutionApplyStatus.ROLLED_BACK
    payload.apply_error = None
    payload.reason_code = "rolled_back"
    payload.remediation = (
        "Review the original content before re-applying this evolution."
    )
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
