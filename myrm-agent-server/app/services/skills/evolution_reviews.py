"""
[INPUT]
- app.database.models.approval::ApprovalRecord (POS: 统一审批记录模型)
- app.database.dto::AgentUpdate (POS: Agent API 契约 DTO)
- app.services.approvals.registry::ApprovalRegistry (POS: 统一审批流调度器。负责将各种拦截节点落库并推送 SSE 事件，接收 resolve 指令。)
- app.services.skills.experience_ledger::record_experience_event (POS: 学习资产事件账本服务)
[OUTPUT]
- EvolutionApprovalPayload / EvolutionReviewRecord / evolution review lifecycle helpers
[POS]
统一的 evolution 审核生命周期服务。以 ApprovalRecord 为唯一事实源，提供幂等落地、回滚与 apply-failed 重试语义。
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timezone
from enum import StrEnum
from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import (
    EvolutionType,
    SkillLineage,
    SkillRecord,
)
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import desc, func, select

from app.core.skills.config_version import bump_skill_config_version
from app.database.connection import get_session
from app.database.dto import AgentUpdate
from app.database.models import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)

logger = logging.getLogger(__name__)

EVOLUTION_ACTION_TYPE = "evolution"


class EvolutionGrowthStatus(StrEnum):
    PENDING_REVIEW = "PENDING_REVIEW"
    FAILED_SCAN = "FAILED_SCAN"
    BLOCKED_LOCKED = "BLOCKED_LOCKED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    APPLY_FAILED = "APPLY_FAILED"


class EvolutionApplyStatus(StrEnum):
    NOT_APPLIED = "NOT_APPLIED"
    APPLIED = "APPLIED"
    FAILED = "FAILED"
    ROLLED_BACK = "ROLLED_BACK"


class RuntimeFailureEvidence(BaseModel):
    source: str = "runtime"
    tool_name: str
    error_signature: str
    tool_args_hash: str | None = None
    loop_kind: str | None = None
    skill_version: str | None = None
    attribution_confidence: float
    failure_count: int = 1
    first_seen_at: str
    last_seen_at: str
    candidate_skill_names: list[str] = Field(default_factory=list)


class EvolutionApprovalPayload(BaseModel):
    schema_version: int = 1
    skill_id: str
    skill_name: str
    skill_path: str
    evolution_type: str
    reason: str
    original_content: str
    evolved_content: str
    confidence: float
    test_passed: bool
    task_context: str | None = None
    trajectory: str | None = None
    growth_status: EvolutionGrowthStatus = EvolutionGrowthStatus.PENDING_REVIEW
    apply_status: EvolutionApplyStatus = EvolutionApplyStatus.NOT_APPLIED
    apply_error: str | None = None
    reject_reason: str | None = None
    reason_code: str | None = "manual_review"
    remediation: str | None = "Review the diff and approve or reject the proposal."
    runtime_failure: RuntimeFailureEvidence | None = None


@dataclass(slots=True)
class EvolutionReviewRecord:
    id: str
    source: str
    skill_id: str
    skill_name: str
    skill_path: str
    evolution_type: str
    reason: str
    original_content: str
    evolved_content: str
    confidence: float
    test_passed: bool
    status: EvolutionGrowthStatus
    approval_status: str
    apply_status: EvolutionApplyStatus
    apply_error: str | None
    reason_code: str | None
    remediation: str | None
    runtime_failure: RuntimeFailureEvidence | None
    trajectory: str | None
    created_at: datetime
    resolved_at: datetime | None


class EvolutionApplyError(RuntimeError):
    """Raised when an approved evolution could not be applied to disk."""


def evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"


def _skill_store_db_path() -> Path:
    from app.config.settings import settings

    return Path(settings.database.state_dir) / "skills.db"


def _get_skill_store() -> SkillStore:
    return SkillStore(db_path=_skill_store_db_path())


def _apply_failure_remediation(skill_name: str) -> str:
    return (
        f'Resolve the file-system issue for "{skill_name}" and retry apply, or reject the proposal if the change should not land.'
    )


def _approval_payload(record: ApprovalRecord) -> EvolutionApprovalPayload | None:
    raw_payload = record.payload if isinstance(record.payload, dict) else {}
    try:
        return EvolutionApprovalPayload.model_validate(raw_payload)
    except ValidationError as exc:
        logger.error("Failed to parse evolution approval payload for %s: %s", record.id, exc)
        return None


def approval_to_evolution_review_record(
    record: ApprovalRecord,
) -> EvolutionReviewRecord | None:
    if record.action_type != EVOLUTION_ACTION_TYPE:
        return None
    payload = _approval_payload(record)
    if payload is None:
        return None
    return EvolutionReviewRecord(
        id=record.id,
        source="approval",
        skill_id=payload.skill_id,
        skill_name=payload.skill_name,
        skill_path=payload.skill_path,
        evolution_type=payload.evolution_type,
        reason=payload.reason,
        original_content=payload.original_content,
        evolved_content=payload.evolved_content,
        confidence=payload.confidence,
        test_passed=payload.test_passed,
        status=payload.growth_status,
        approval_status=record.status,
        apply_status=payload.apply_status,
        apply_error=payload.apply_error,
        reason_code=payload.reason_code,
        remediation=payload.remediation,
        runtime_failure=payload.runtime_failure,
        trajectory=payload.trajectory,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
    )


def _runtime_failure_ledger_event(
    growth_status: EvolutionGrowthStatus,
) -> ExperienceEventType:
    if growth_status == EvolutionGrowthStatus.FAILED_SCAN:
        return ExperienceEventType.SKILL_GROWTH_FAILED_SCAN
    if growth_status == EvolutionGrowthStatus.BLOCKED_LOCKED:
        return ExperienceEventType.SKILL_GROWTH_BLOCKED
    if growth_status == EvolutionGrowthStatus.REJECTED:
        return ExperienceEventType.EVOLUTION_REJECTED
    return ExperienceEventType.EVOLUTION_PENDING


def _creation_outcome(growth_status: EvolutionGrowthStatus) -> str:
    if growth_status == EvolutionGrowthStatus.PENDING_REVIEW:
        return "pending"
    return growth_status.value.lower()


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
            event_type=_runtime_failure_ledger_event(growth_status),
            entity_type=ExperienceEntityType.EVOLUTION,
            entity_id=record.id,
            lineage_id=evolution_lineage_id(record.id),
            outcome=_creation_outcome(growth_status),
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


async def _list_approval_records() -> list[EvolutionReviewRecord]:
    async with get_session() as db:
        result = await db.execute(
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
            .order_by(desc(ApprovalRecord.created_at))
        )
        records = list(result.scalars().all())
    items: list[EvolutionReviewRecord] = []
    for record in records:
        review_record = approval_to_evolution_review_record(record)
        if review_record is not None:
            items.append(review_record)
    return items


async def list_evolution_review_records(
    *,
    limit: int = 50,
    pending_only: bool = False,
) -> list[EvolutionReviewRecord]:
    items = await _list_approval_records()
    if pending_only:
        items = [
            item
            for item in items
            if item.status
            in {
                EvolutionGrowthStatus.PENDING_REVIEW,
                EvolutionGrowthStatus.APPLY_FAILED,
            }
        ]
    return items[:limit]


async def count_evolution_review_records(*, pending_only: bool = False) -> int:
    if pending_only:
        return len(await list_evolution_review_records(pending_only=True))

    async with get_session() as db:
        stmt = select(func.count()).select_from(ApprovalRecord).where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
        result = await db.execute(stmt)
        return result.scalar() or 0


async def find_runtime_failure_review_record(
    *,
    skill_id: str,
    error_signature: str,
    skill_version: str | None,
) -> EvolutionReviewRecord | None:
    async with get_session() as db:
        stmt = (
            select(ApprovalRecord)
            .where(ApprovalRecord.action_type == EVOLUTION_ACTION_TYPE)
            .where(ApprovalRecord.payload["skill_id"].as_string() == skill_id)
            .where(ApprovalRecord.payload["runtime_failure"]["error_signature"].as_string() == error_signature)
            .order_by(desc(ApprovalRecord.created_at))
        )
        if skill_version is not None:
            stmt = stmt.where(ApprovalRecord.payload["runtime_failure"]["skill_version"].as_string() == skill_version)
        result = await db.execute(stmt)
        records = list(result.scalars().all())

    for record in records:
        payload = _approval_payload(record)
        if payload is None or payload.runtime_failure is None:
            continue
        if payload.skill_id != skill_id:
            continue
        if payload.runtime_failure.error_signature != error_signature:
            continue
        if skill_version is not None and payload.runtime_failure.skill_version != skill_version:
            continue
        if payload.growth_status in {
            EvolutionGrowthStatus.PENDING_REVIEW,
            EvolutionGrowthStatus.APPLY_FAILED,
            EvolutionGrowthStatus.FAILED_SCAN,
            EvolutionGrowthStatus.BLOCKED_LOCKED,
        }:
            return approval_to_evolution_review_record(record)
    return None


async def bump_runtime_failure_review_record(
    *,
    evolution_id: str,
    last_seen_at: str,
) -> EvolutionReviewRecord | None:
    record = await _load_approval_record(evolution_id)
    if record is None:
        return None

    payload = _approval_payload(record)
    if payload is None or payload.runtime_failure is None:
        return None

    payload.runtime_failure.failure_count += 1
    payload.runtime_failure.last_seen_at = last_seen_at
    updated = await _persist_approval_payload(record.id, payload=payload)
    return approval_to_evolution_review_record(updated)


async def get_evolution_review_record(
    evolution_id: str,
) -> EvolutionReviewRecord | None:
    async with get_session() as db:
        approval = await db.get(ApprovalRecord, evolution_id)
        if approval is not None and approval.action_type == EVOLUTION_ACTION_TYPE:
            return approval_to_evolution_review_record(approval)
    return None


async def _load_approval_record(evolution_id: str) -> ApprovalRecord | None:
    async with get_session() as db:
        record = await db.get(ApprovalRecord, evolution_id)
        if record is None or record.action_type != EVOLUTION_ACTION_TYPE:
            return None
        return record


async def _persist_approval_payload(
    evolution_id: str,
    *,
    approval_status: str | None = None,
    payload: EvolutionApprovalPayload | None = None,
    resolved_at: datetime | None | object = ...,
) -> ApprovalRecord:
    async with get_session() as db:
        record = await db.get(ApprovalRecord, evolution_id)
        if record is None or record.action_type != EVOLUTION_ACTION_TYPE:
            raise RuntimeError(f"Evolution approval record not found: {evolution_id}")
        if approval_status is not None:
            record.status = approval_status
        if payload is not None:
            record.payload = payload.model_dump(mode="json")
        if resolved_at is not ...:
            record.resolved_at = resolved_at
        await db.commit()
        await db.refresh(record)
        return record


async def _enqueue_cognitive_subsumption(payload: EvolutionApprovalPayload) -> None:
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


async def _apply_to_disk_and_store(payload: EvolutionApprovalPayload, agent_id: str | None = None) -> None:
    store = _get_skill_store()
    try:
        if payload.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION.value:
            await _apply_description_update(payload, store, agent_id)
        else:
            await _apply_content_update(payload, store, agent_id)
    finally:
        store.close()

    try:
        await _enqueue_cognitive_subsumption(payload)
    except Exception as exc:
        logger.warning("Failed to enqueue cognitive_subsumption task: %s", exc)

    bump_skill_config_version()


async def _apply_description_update(payload: EvolutionApprovalPayload, store: SkillStore, agent_id: str | None = None) -> None:
    """Apply a description-only update: update SkillStore description without touching the file."""
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
        from myrm_agent_harness.agent.skills.evolution.core.types import EnvironmentFingerprint

        if existing.environment is None:
            existing.environment = EnvironmentFingerprint()
        existing.environment.custom_tags["scope_agent_id"] = agent_id

    await store.save_skill(existing)


async def _apply_content_update(payload: EvolutionApprovalPayload, store: SkillStore, agent_id: str | None = None) -> None:
    """Apply a full content update: write to disk and update SkillStore."""
    skill_path = Path(payload.skill_path)
    if skill_path.exists():
        backup_path = skill_path.with_suffix(skill_path.suffix + ".bak")
        shutil.copy2(skill_path, backup_path)

    existing = store.get_skill(payload.skill_id)

    # 1. Determine if Copy-on-Write Forking is needed
    is_fork = False
    old_skill_id = payload.skill_id
    final_scope_agent_id = None

    if existing and existing.environment and "scope_agent_id" in existing.environment.custom_tags:
        owner_id = existing.environment.custom_tags["scope_agent_id"]
        if agent_id and owner_id != agent_id:
            # Non-owner is trying to evolve a scoped skill -> FORK!
            is_fork = True
            import uuid

            payload.skill_id = f"fork_{uuid.uuid4().hex[:8]}"
            payload.skill_name = f"{payload.skill_name}-fork"
            orig_path = Path(payload.skill_path)
            # Change directory to the new fork name
            skill_path = orig_path.parent.parent / payload.skill_name / orig_path.name
            payload.skill_path = str(skill_path)
            # A fork is a new file, so rollback should delete it
            payload.original_content = ""
            existing = None  # We are writing a new skill, so `existing` is nullified for the target
            final_scope_agent_id = agent_id
        else:
            final_scope_agent_id = owner_id
    elif payload.evolution_type in (EvolutionType.CAPTURED.value, EvolutionType.SLICE_EXTRACTION.value) and agent_id:
        final_scope_agent_id = agent_id

    content_to_write = payload.evolved_content
    if final_scope_agent_id:
        import re

        # Inject scope_agent_id into frontmatter if it exists
        def _inject_scope(match: re.Match) -> str:
            fm = match.group(1)
            # Remove any existing scope_agent_id
            fm = re.sub(r"(?m)^scope_agent_id:\s*.*$", "", fm)
            return f"---\n{fm.strip()}\nscope_agent_id: {final_scope_agent_id}\n---"

        content_to_write = re.sub(r"^---\s*\n(.*?)\n---", _inject_scope, content_to_write, count=1, flags=re.DOTALL)

    skill_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=skill_path.parent, prefix="skill_evolve_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
            file_obj.write(content_to_write)
        os.replace(temp_path, skill_path)
    except Exception:
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

    lineage = SkillLineage(
        parent_id=payload.skill_id,
        evolution_type=EvolutionType(payload.evolution_type),
        change_summary=payload.reason,
        created_at=datetime.now(),
        created_by="evolution_engine",
    )

    if existing:
        skill_record = existing
        skill_record.content = payload.evolved_content
        skill_record.lineage = lineage
        skill_record.is_active = True
        # Preserve metrics, traps, verification_steps, etc.
        if final_scope_agent_id:
            if skill_record.environment is None:
                from myrm_agent_harness.agent.skills.evolution.core.types import EnvironmentFingerprint

                skill_record.environment = EnvironmentFingerprint()
            skill_record.environment.custom_tags["scope_agent_id"] = final_scope_agent_id
    else:
        from myrm_agent_harness.agent.skills.evolution.core.types import EnvironmentFingerprint

        env = EnvironmentFingerprint()
        if final_scope_agent_id:
            env.custom_tags["scope_agent_id"] = final_scope_agent_id

        skill_record = SkillRecord(
            skill_id=payload.skill_id,
            name=payload.skill_name,
            description="Auto-evolved skill",
            content=payload.evolved_content,
            path=str(skill_path),
            lineage=lineage,
            is_active=True,
            environment=env,
        )

    await store.save_skill(skill_record)

    if is_fork and agent_id:
        try:
            from app.database.connection import get_session
            from app.database.models import Agent

            async with get_session() as db:
                agent = await db.get(Agent, agent_id)
                if agent:
                    # Update mounted_skill_ids to use the new fork
                    if agent.mounted_skill_ids and old_skill_id in agent.mounted_skill_ids:
                        new_mounted = [x for x in agent.mounted_skill_ids if x != old_skill_id]
                        agent.mounted_skill_ids = new_mounted
                        new_skill_ids = list(agent.skill_ids) if agent.skill_ids else []
                        if payload.skill_id not in new_skill_ids:
                            new_skill_ids.append(payload.skill_id)
                        agent.skill_ids = new_skill_ids
                    # If it was in skill_ids (e.g., global skill evolved by agent)
                    elif agent.skill_ids and old_skill_id in agent.skill_ids:
                        agent.skill_ids = [x if x != old_skill_id else payload.skill_id for x in agent.skill_ids]

                    # Update ORM JSON columns
                    from sqlalchemy.orm.attributes import flag_modified

                    flag_modified(agent, "mounted_skill_ids")
                    flag_modified(agent, "skill_ids")
                    await db.commit()
        except Exception as e:
            logger.error("Failed to update agent skill bindings during Copy-on-Write forking: %s", e)


async def _mark_apply_failure(
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
    payload.remediation = _apply_failure_remediation(payload.skill_name)
    approval_status = "APPROVED"
    if auto_approved:
        approval_status = "PENDING"
    updated = await _persist_approval_payload(
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


async def _apply_approval_record(
    record: ApprovalRecord,
    *,
    auto_approved: bool,
) -> EvolutionReviewRecord:
    payload = _approval_payload(record)
    if payload is None:
        raise EvolutionApplyError("Evolution approval payload is invalid.")

    try:
        await _apply_to_disk_and_store(payload, agent_id=record.agent_id)
    except Exception as exc:
        await _mark_apply_failure(record, payload, str(exc), auto_approved=auto_approved)
        raise EvolutionApplyError(str(exc)) from exc

    payload.apply_status = EvolutionApplyStatus.APPLIED
    payload.apply_error = None
    payload.remediation = None
    payload.reason_code = None if payload.growth_status == EvolutionGrowthStatus.APPROVED else payload.reason_code
    payload.growth_status = EvolutionGrowthStatus.APPROVED

    updated = await _persist_approval_payload(
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


async def approve_evolution_review_record(
    evolution_id: str,
    *,
    auto_approved: bool = False,
) -> EvolutionReviewRecord:
    approval_record = await _load_approval_record(evolution_id)
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

    return await _apply_approval_record(record, auto_approved=auto_approved)


async def reject_evolution_review_record(
    evolution_id: str,
    *,
    reason: str | None = None,
) -> EvolutionReviewRecord:
    approval_record = await _load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")

    payload = _approval_payload(approval_record)
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
        approval_record = await _persist_approval_payload(
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
        store = _get_skill_store()
        try:
            await store.add_evolution_constraint(payload.skill_id, reason.strip())
        finally:
            store.close()

    review_record = approval_to_evolution_review_record(approval_record)
    if review_record is None:
        raise EvolutionApplyError(f"Failed to normalize rejected evolution record: {approval_record.id}")
    return review_record


async def rollback_evolution_review_record(evolution_id: str) -> dict[str, object]:
    approval_record = await _load_approval_record(evolution_id)
    if approval_record is None:
        raise EvolutionApplyError(f"Evolution approval record not found: {evolution_id}")

    payload = _approval_payload(approval_record)
    if payload is None:
        raise EvolutionApplyError(f"Invalid evolution approval record: {evolution_id}")
    if payload.apply_status != EvolutionApplyStatus.APPLIED:
        raise EvolutionApplyError("Only applied evolutions can be rolled back.")

    store = _get_skill_store()
    try:
        if payload.evolution_type == EvolutionType.OPTIMIZE_DESCRIPTION.value:
            await _rollback_description_update(payload, store)
        else:
            await _rollback_content_update(payload, store)
    finally:
        store.close()

    payload.apply_status = EvolutionApplyStatus.ROLLED_BACK
    payload.apply_error = None
    payload.reason_code = "rolled_back"
    payload.remediation = "Review the original content before re-applying this evolution."
    await _persist_approval_payload(
        evolution_id,
        approval_status="APPROVED",
        payload=payload,
        resolved_at=approval_record.resolved_at,
    )
    bump_skill_config_version()
    return {"status": "rolled_back", "evolution_id": evolution_id}


async def _rollback_description_update(payload: EvolutionApprovalPayload, store: SkillStore) -> None:
    """Rollback a description-only update: restore original description in SkillStore."""
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


async def _rollback_content_update(payload: EvolutionApprovalPayload, store: SkillStore) -> None:
    """Rollback a full content update: restore file and SkillStore."""
    skill_path = Path(payload.skill_path)

    # If it is a derived fork (or original_content was forcibly empty), we delete the skill
    if payload.evolution_type == EvolutionType.DERIVED.value or not payload.original_content:
        # Before deleting, check if we need to restore agent mount pointing
        fork_skill = store.get_skill(payload.skill_id)
        owner_id = None
        parent_id = None
        if fork_skill:
            if fork_skill.environment and "scope_agent_id" in fork_skill.environment.custom_tags:
                owner_id = fork_skill.environment.custom_tags["scope_agent_id"]
            if fork_skill.lineage:
                parent_id = fork_skill.lineage.parent_id

        if skill_path.exists():
            # If it's a derived skill, it's inside a folder like skill_name-fork/SKILL.md
            if skill_path.name == "SKILL.md":
                if skill_path.parent.name not in ["workspace", "skills", ""]:
                    shutil.rmtree(skill_path.parent, ignore_errors=True)
                else:
                    logger.warning("Skipping rmtree on unsafe path during rollback: %s", skill_path.parent)
            else:
                os.remove(skill_path)
        try:
            await store.delete_skill(payload.skill_id)
        except Exception as exc:
            logger.warning("Failed to delete skill from DB during rollback: %s", exc)

        # Restore the original mount for the agent if we know who owned the fork
        if owner_id and parent_id:
            try:
                from app.services.agent.agent_service import agent_service

                agent = await agent_service.get_agent(owner_id)
                if agent:
                    mounted_ids = agent.mounted_skill_ids or []
                    skill_ids = agent.skill_ids or []
                    update_needed = False

                    if payload.skill_id in skill_ids:
                        skill_ids = [x for x in skill_ids if x != payload.skill_id]

                        # Determine if parent was globally owned by this agent or mounted
                        parent_skill = store.get_skill(parent_id)
                        parent_owner_id = None
                        if parent_skill and parent_skill.environment and "scope_agent_id" in parent_skill.environment.custom_tags:
                            parent_owner_id = parent_skill.environment.custom_tags["scope_agent_id"]

                        # If parent is explicitly scoped to this exact agent (or it has no scope so it's a true global),
                        # it belongs in skill_ids. Wait, if it has no scope, it's global, so it doesn't need to be in either,
                        # but if they had it in skill_ids, let's restore it there.
                        # The simplest rule: if parent_owner_id != owner_id, it is a cross-agent mount.
                        if parent_owner_id and parent_owner_id != owner_id:
                            if parent_id not in mounted_ids:
                                mounted_ids.append(parent_id)
                        else:
                            if parent_id not in skill_ids:
                                skill_ids.append(parent_id)

                        update_needed = True

                    if update_needed:
                        await agent_service.update_agent(
                            owner_id, AgentUpdate(mounted_skill_ids=mounted_ids, skill_ids=skill_ids)
                        )
            except Exception as e:
                logger.error("Failed to restore parent mount during rollback: %s", e)
    else:
        fd, temp_path = tempfile.mkstemp(dir=skill_path.parent, prefix="skill_rollback_")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file_obj:
                file_obj.write(payload.original_content)
            os.replace(temp_path, skill_path)
        except Exception:
            if os.path.exists(temp_path):
                os.remove(temp_path)
            raise

        lineage = SkillLineage(
            evolution_type=EvolutionType(payload.evolution_type),
            version=1,
            parent_id=None,
            change_summary="Rolled back",
            created_at=datetime.now(UTC),
            created_by="user",
        )
        skill_record = SkillRecord(
            skill_id=payload.skill_id,
            name=payload.skill_name,
            description="",
            content=payload.original_content,
            path=str(skill_path),
            lineage=lineage,
            is_active=True,
        )
        await store.save_skill(skill_record)
