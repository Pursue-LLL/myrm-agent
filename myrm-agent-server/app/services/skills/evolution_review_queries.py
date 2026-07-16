"""
[INPUT]
- app.services.approvals.registry::ApprovalRegistry
- app.services.skills.evolution_review_persistence
[OUTPUT]
- create/list/count/find/get evolution review records
[POS]
Evolution 审核记录创建与只读查询（ApprovalRecord 为事实源）。
"""

from __future__ import annotations

from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.evolution_review_persistence import (
    count_approval_review_records,
    filter_runtime_failure_record,
    find_matching_approval_records,
    list_approval_review_records,
    load_approval_record,
    persist_approval_payload,
)
from app.services.skills.evolution_review_types import (
    EVOLUTION_ACTION_TYPE,
    MAX_SKILL_CONTENT_CHARS,
    EvolutionApplyError,
    EvolutionApprovalPayload,
    EvolutionGrowthStatus,
    EvolutionReviewRecord,
    RuntimeFailureEvidence,
    approval_payload,
    approval_to_evolution_review_record,
    creation_outcome,
    evolution_lineage_id,
    runtime_failure_ledger_event,
)
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceLedgerWrite,
    record_experience_event,
)


async def create_evolution_review_record(
    *,
    agent_id: str,
    chat_id: str | None,
    proposal_skill_id: str,
    skill_name: str,
    skill_path: str,
    evolution_type: str,
    reason: str,
    original_content: str,
    evolved_content: str,
    confidence: float,
    test_passed: bool,
    task_context: str | None,
    trajectory: str | None = None,
    reason_code: str | None = None,
    remediation: str | None = None,
    runtime_failure: RuntimeFailureEvidence | None = None,
    growth_status: EvolutionGrowthStatus = EvolutionGrowthStatus.PENDING_REVIEW,
    approval_status: str = "PENDING",
) -> EvolutionReviewRecord:
    if evolved_content and len(evolved_content) > MAX_SKILL_CONTENT_CHARS:
        raise EvolutionApplyError(
            f"Evolved content too large ({len(evolved_content)} chars, max {MAX_SKILL_CONTENT_CHARS})."
        )

    payload = EvolutionApprovalPayload(
        skill_id=proposal_skill_id,
        skill_name=skill_name,
        skill_path=skill_path,
        evolution_type=evolution_type,
        reason=reason,
        original_content=original_content,
        evolved_content=evolved_content,
        confidence=confidence,
        test_passed=test_passed,
        task_context=task_context,
        trajectory=trajectory,
        growth_status=growth_status,
        reason_code=reason_code or "manual_review",
        remediation=remediation or "Review the diff and approve or reject the proposal.",
        runtime_failure=runtime_failure,
    )
    record = await ApprovalRegistry.create_approval(
        agent_id=agent_id,
        action_type=EVOLUTION_ACTION_TYPE,
        payload=payload.model_dump(mode="json"),
        reason=reason,
        severity="warning",
        chat_id=chat_id,
        status=approval_status,
    )
    await record_experience_event(
        ExperienceLedgerWrite(
            event_type=runtime_failure_ledger_event(growth_status),
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=record.id,
            lineage_id=evolution_lineage_id(record.id),
            outcome=creation_outcome(growth_status),
            summary=reason,
            artifact_refs={"skill_id": proposal_skill_id, "skill_name": skill_name},
            metrics_snapshot={"confidence": confidence, "test_passed": test_passed},
            detail={
                "evolution_type": evolution_type,
                "task_context": task_context,
                "apply_status": payload.apply_status.value,
                "reason_code": payload.reason_code,
                "remediation": payload.remediation,
                "runtime_failure": (runtime_failure.model_dump(mode="json") if runtime_failure is not None else None),
            },
        )
    )
    review_record = approval_to_evolution_review_record(record)
    if review_record is None:
        raise RuntimeError(f"Failed to normalize evolution approval record: {record.id}")
    return review_record


async def list_evolution_review_records(
    *,
    limit: int = 50,
    pending_only: bool = False,
) -> list[EvolutionReviewRecord]:
    return await list_approval_review_records(limit=limit, pending_only=pending_only)


async def count_evolution_review_records(*, pending_only: bool = False) -> int:
    return await count_approval_review_records(pending_only=pending_only)


async def find_runtime_failure_review_record(
    *,
    skill_id: str,
    error_signature: str,
    skill_version: str | None,
) -> EvolutionReviewRecord | None:
    records = await find_matching_approval_records(
        skill_id=skill_id,
        error_signature=error_signature,
        skill_version=skill_version,
    )
    return filter_runtime_failure_record(
        records,
        skill_id=skill_id,
        error_signature=error_signature,
        skill_version=skill_version,
        open_statuses={
            EvolutionGrowthStatus.PENDING_REVIEW,
            EvolutionGrowthStatus.APPLY_FAILED,
            EvolutionGrowthStatus.FAILED_SCAN,
            EvolutionGrowthStatus.BLOCKED_LOCKED,
        },
    )


async def bump_runtime_failure_review_record(
    *,
    evolution_id: str,
    last_seen_at: str,
) -> EvolutionReviewRecord | None:
    record = await load_approval_record(evolution_id)
    if record is None:
        return None

    payload = approval_payload(record)
    if payload is None or payload.runtime_failure is None:
        return None

    payload.runtime_failure.failure_count += 1
    payload.runtime_failure.last_seen_at = last_seen_at
    updated = await persist_approval_payload(record.id, payload=payload)
    return approval_to_evolution_review_record(updated)


async def get_evolution_review_record(
    evolution_id: str,
) -> EvolutionReviewRecord | None:
    async with get_session() as db:
        approval = await db.get(ApprovalRecord, evolution_id)
        if approval is not None and approval.action_type == EVOLUTION_ACTION_TYPE:
            return approval_to_evolution_review_record(approval)
    return None
