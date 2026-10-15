"""Skill drafts HTTP API.

Exposes REST endpoints for listing and reviewing skill growth drafts
(pending/approved/rejected), materializing approved skills, and emitting
front-end refresh events through the single-source publish helpers.

[INPUT]
- app.database.connection::get_session (POS: 数据库连接管理)
- app.services.approvals.registry::ApprovalRegistry (POS: 统一的拦截审批注册与唤醒中枢)
- app.services.skills.draft_notification::publish_skill_growth_event (POS: SKILL_GROWTH_UPDATED 前端刷新事件单一出口)
- app.services.skills.evolution_events::publish_skill_evolved_event (POS: SKILL_EVOLVED 前端刷新事件单一出口)
- app.services.skills.experience_ledger::record_skill_growth_event (POS: 学习资产事件账本)
- app.api.skills.draft_materialize::materialize_skill_draft,materialize_skill_patch,materialize_semantic_memory (POS: 技能草稿落地：新技能写盘、补丁应用、语义记忆写入)
- app.api.skills.draft_record::SkillDraftRecord (POS: 技能草稿记录视图)

[OUTPUT]
- GET /drafts: 草稿分页列表 + 未审核计数
- POST /drafts/{draft_id}/approve: 审批通过 → 技能落地（已归档的同名技能一并恢复）+ 前端事件
- POST /drafts/{draft_id}/reject: 审批拒绝 → 账本负向事件 + 前端事件

[POS]
技能草稿 HTTP API：草稿列表、审批通过/拒绝、状态流转与前端刷新事件发布（落地写入见 draft_materialize）。
"""

from __future__ import annotations

import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm.attributes import flag_modified

from app.api.skills.draft_materialize import (
    materialize_semantic_memory,
    materialize_skill_draft,
    materialize_skill_patch,
)
from app.api.skills.draft_record import SkillDraftRecord
from app.database.connection import get_session
from app.database.models import Agent, ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry
from app.services.skills.draft_notification import publish_skill_growth_event
from app.services.skills.evolution_events import publish_skill_evolved_event
from app.services.skills.experience_ledger import record_skill_growth_event
from app.services.skills.growth.constants import GROWTH_ACTION_TYPES

logger = logging.getLogger(__name__)
router = APIRouter()
_TEST_MOCK_DRAFT_NAMES: tuple[str, str] = (
    "test-frontend-approve",
    "test-frontend-reject",
)


class SkillDraftResponse(BaseModel):
    id: str
    agent_id: str
    chat_id: str | None
    draft_type: str
    name: str | None
    description: str | None
    trigger_condition: str | None
    skill_steps: str | None
    content: str | None
    status: str
    reviewed_at: datetime | None
    created_at: datetime
    eval_cases: list[dict[str, object]] = []

    class Config:
        from_attributes = True


class SkillDraftListResponse(BaseModel):
    drafts: list[SkillDraftResponse]
    total: int


class ApproveDraftRequest(BaseModel):
    skill_name: str | None = None
    scope_agent_id: str | None = None


def _payload_text(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    return None


def _approval_growth_status(record: ApprovalRecord) -> str:
    payload_status = record.payload.get("growth_status")
    if isinstance(payload_status, str) and payload_status:
        return payload_status
    if record.status == "APPROVED":
        return "APPROVED"
    if record.status == "REJECTED":
        return "REJECTED"
    return "PENDING_REVIEW"


def _to_skill_draft_record(record: ApprovalRecord) -> SkillDraftRecord:
    payload = record.payload if isinstance(record.payload, dict) else {}
    eval_cases = payload.get("eval_cases")
    return SkillDraftRecord(
        id=record.id,
        agent_id=record.agent_id,
        chat_id=record.chat_id,
        draft_type=record.action_type,
        name=_payload_text(payload, "skill_name"),
        description=record.reason or _payload_text(payload, "description"),
        trigger_condition=_payload_text(payload, "trigger_condition"),
        skill_steps=_payload_text(payload, "skill_steps"),
        content=_payload_text(payload, "patch_content") or _payload_text(payload, "content"),
        status=_approval_growth_status(record),
        reviewed_at=record.resolved_at,
        created_at=record.created_at,
        approval_status=record.status,
        eval_cases=eval_cases if isinstance(eval_cases, list) else None,
    )


def _skill_draft_response(draft: SkillDraftRecord) -> SkillDraftResponse:
    return SkillDraftResponse(
        id=draft.id,
        agent_id=draft.agent_id,
        chat_id=draft.chat_id,
        draft_type=draft.draft_type,
        name=draft.name,
        description=draft.description,
        trigger_condition=draft.trigger_condition,
        skill_steps=draft.skill_steps,
        content=draft.content,
        status=draft.status,
        reviewed_at=draft.reviewed_at,
        created_at=draft.created_at,
        eval_cases=draft.eval_cases or [],
    )


def _publish_draft_event(draft: SkillDraftRecord) -> None:
    """Publish the SKILL_GROWTH_UPDATED refresh event for a draft record."""
    publish_skill_growth_event(
        case_id=draft.id,
        draft_type=draft.draft_type,
        status=draft.status,
        name=draft.name or draft.draft_type,
    )


async def _get_approval_skill_draft(draft_id: str) -> ApprovalRecord | None:
    async with get_session() as db:
        result = await db.execute(
            select(ApprovalRecord).where(
                ApprovalRecord.id == draft_id,
                ApprovalRecord.action_type.in_(GROWTH_ACTION_TYPES),
            )
        )
        return result.scalar_one_or_none()


async def get_skill_drafts(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[SkillDraftRecord], int]:
    """Query skill drafts with optional lifecycle status filter."""
    async with get_session() as db:
        stmt = (
            select(ApprovalRecord)
            .where(
                ApprovalRecord.action_type.in_(GROWTH_ACTION_TYPES),
            )
            .order_by(ApprovalRecord.created_at.desc())
        )
        result = await db.execute(stmt)
        records = list(result.scalars().all())

    drafts = [_to_skill_draft_record(record) for record in records]
    if status:
        drafts = [draft for draft in drafts if draft.status == status]
    total = len(drafts)
    return drafts[offset : offset + limit], total


@router.get("/drafts", response_model=SkillDraftListResponse)
async def list_skill_drafts(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> SkillDraftListResponse:
    """List skill drafts for a user (optionally filtered by status)."""
    drafts, total = await get_skill_drafts(status=status, limit=limit, offset=offset)
    return SkillDraftListResponse(
        drafts=[_skill_draft_response(draft) for draft in drafts],
        total=total,
    )


@router.get("/drafts/unreviewed/count")
async def get_unreviewed_draft_count() -> dict[str, object]:
    """Get count of unreviewed skill drafts (for badge notification)."""
    async with get_session() as db:
        result = await db.execute(
            select(ApprovalRecord).where(
                ApprovalRecord.status == "PENDING",
                ApprovalRecord.action_type.in_(GROWTH_ACTION_TYPES),
            )
        )
        count = sum(1 for record in result.scalars().all() if _approval_growth_status(record) == "PENDING_REVIEW")
    return {"unreviewed_count": count}


def _namespace_mock_names(namespace: str) -> tuple[str, str]:
    if not namespace.strip():
        return _TEST_MOCK_DRAFT_NAMES
    suffix = namespace.strip()[:16]
    return (
        f"test-frontend-approve-{suffix}",
        f"test-frontend-reject-{suffix}",
    )


async def seed_mock_drafts_for_e2e(agent_id: str = "default", namespace: str = "") -> dict[str, object]:
    """Create two predictable mock drafts for Instinct Inbox UI E2E tests.

    ``namespace`` isolates parallel Chrome E2E runs: mock names are suffixed and
    cleanup only touches drafts owned by the same namespace, so concurrent
    sessions never deny each other's seeds (SSOT: SHARED+NAMESPACE_WRITE).
    """
    approve_name, reject_name = _namespace_mock_names(namespace)
    names = (approve_name, reject_name)
    drafts, _ = await get_skill_drafts(status="PENDING_REVIEW", limit=500)
    for draft in drafts:
        if draft.name in names:
            await ApprovalRegistry.resolve_approval(draft.id, "deny")

    created_ids: list[str] = []
    mock_specs = (
        (
            approve_name,
            f"This is a test skill for UI Approve button ({approve_name}).",
            f'```markdown\n---\nname: {approve_name}\ndescription: "approve test"\n---\n\n# Rules\nApprove rules\n```',
            "Test draft approve UI",
        ),
        (
            reject_name,
            f"This is a test skill for UI Reject button ({reject_name}).",
            f'```markdown\n---\nname: {reject_name}\ndescription: "reject test"\n---\n\n# Rules\nReject rules\n```',
            "Test draft reject UI",
        ),
    )
    chat_id = f"test_chat_{namespace.strip()[:16]}" if namespace.strip() else "test_chat_123"
    for skill_name, description, content, reason in mock_specs:
        record = await ApprovalRegistry.create_approval(
            agent_id=agent_id,
            chat_id=chat_id,
            action_type="skill_draft",
            payload={
                "skill_name": skill_name,
                "description": description,
                "content": content,
                "score": 0.95,
            },
            reason=reason,
        )
        created_ids.append(record.id)

    return {"created_ids": created_ids, "skill_names": list(names)}


@router.post("/drafts/test/seed-mock", include_in_schema=False)
async def seed_test_mock_drafts(
    agent_id: str = "default",
    namespace: str = "",
) -> dict[str, object]:
    """Local dev/test only: reset and seed Instinct Inbox E2E mock drafts."""
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")
    return await seed_mock_drafts_for_e2e(agent_id=agent_id, namespace=namespace)


@router.get("/drafts/{draft_id}", response_model=SkillDraftResponse)
async def get_skill_draft(draft_id: str) -> SkillDraftResponse:
    """Get a single skill draft by ID."""
    record = await _get_approval_skill_draft(draft_id)
    if not record:
        raise HTTPException(status_code=404, detail="Draft not found")
    return _skill_draft_response(_to_skill_draft_record(record))


@router.post("/drafts/{draft_id}/approve")
async def approve_skill_draft(
    draft_id: str,
    request: ApproveDraftRequest,
) -> dict[str, str | bool | None]:
    """Approve a skill draft and materialize it as a real skill or memory."""
    record = await _get_approval_skill_draft(draft_id)
    if not record:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft = _to_skill_draft_record(record)
    if draft.status != "PENDING_REVIEW":
        raise HTTPException(status_code=400, detail=f"Cannot approve draft in status: {draft.status}")

    if draft.draft_type in {"skill_draft", "skill_patch"}:
        # Local skill writes are disabled in sandbox — materialization would
        # otherwise persist to a store the agent can never load. Delayed import
        # avoids a circular import through app.api.skills.router when this
        # module is loaded standalone by tests.
        from app.api.skills._deploy_capability import require_local_skills_capability

        require_local_skills_capability()

    resolved = await ApprovalRegistry.resolve_approval(
        approval_id=draft_id,
        decision="approve",
        edited_payload={"growth_status": "APPROVED"},
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    approved_draft = _to_skill_draft_record(resolved)
    materialized: dict[str, str | bool | None] = {"id": draft_id, "status": "APPROVED"}

    if approved_draft.draft_type == "skill_draft":
        mat_result = await materialize_skill_draft(approved_draft, request.skill_name)
    elif approved_draft.draft_type == "skill_patch":
        mat_result = await materialize_skill_patch(approved_draft)
    elif approved_draft.draft_type == "semantic_memory":
        mat_result = await materialize_semantic_memory(approved_draft)
    else:
        mat_result = {}

    if mat_result and not mat_result.get("materialized"):
        await _rollback_draft_status(draft_id)
        pending_record = await _get_approval_skill_draft(draft_id)
        if pending_record is not None:
            pending_draft = _to_skill_draft_record(pending_record)
            _publish_draft_event(pending_draft)
    else:
        await record_skill_growth_event(
            entity_id=approved_draft.id,
            draft_type=approved_draft.draft_type,
            status="APPROVED",
            skill_name=request.skill_name or approved_draft.name,
            summary=approved_draft.description or approved_draft.name or approved_draft.draft_type,
            detail={"approval_status": approved_draft.approval_status},
        )
        _publish_draft_event(approved_draft)

        if approved_draft.draft_type in {"skill_draft", "skill_patch"} and approved_draft.name:
            publish_skill_evolved_event(
                skill_name=request.skill_name or approved_draft.name,
                evolution_type=("new" if approved_draft.draft_type == "skill_draft" else "patch"),
                description=approved_draft.description or approved_draft.name,
            )

        skill_id = mat_result.get("skill_id")
        if skill_id:
            target_agent_id = request.scope_agent_id or approved_draft.agent_id
            await _bind_skill_to_agent(str(skill_id), target_agent_id)

    materialized.update(mat_result)
    return materialized


async def _bind_skill_to_agent(skill_id: str, agent_id: str | None) -> None:
    """Add a materialized skill to the originating Agent's skill_ids."""
    if not agent_id:
        return
    try:
        async with get_session() as db:
            agent = await db.get(Agent, agent_id)
            if agent is None:
                logger.warning("Agent %s not found for skill binding, skipping", agent_id)
                return
            current_ids: list[str] = list(agent.skill_ids) if agent.skill_ids else []
            if skill_id not in current_ids:
                current_ids.append(skill_id)
                agent.skill_ids = current_ids
                flag_modified(agent, "skill_ids")
                await db.commit()
                logger.info("Bound skill %s to agent %s", skill_id, agent_id)
    except Exception as exc:
        logger.error("Failed to bind skill %s to agent %s: %s", skill_id, agent_id, exc)


async def _rollback_draft_status(draft_id: str) -> None:
    """Revert a draft to PENDING_REVIEW after materialization failure."""
    try:
        async with get_session() as db:
            result = await db.execute(select(ApprovalRecord).where(ApprovalRecord.id == draft_id))
            draft = result.scalar_one_or_none()
            if draft is not None:
                draft.status = "PENDING"
                payload = dict(draft.payload)
                payload["growth_status"] = "PENDING_REVIEW"
                draft.payload = payload
                draft.resolved_at = None
                await db.commit()
    except Exception as e:
        logger.error("Failed to rollback draft %s status: %s", draft_id, e)


@router.post("/drafts/{draft_id}/reject")
async def reject_skill_draft(draft_id: str) -> dict[str, object]:
    """Reject a skill draft (marks as rejected, does not delete)."""
    record = await _get_approval_skill_draft(draft_id)
    if not record:
        raise HTTPException(status_code=404, detail="Draft not found")

    draft = _to_skill_draft_record(record)
    if draft.status != "PENDING_REVIEW":
        raise HTTPException(status_code=400, detail=f"Cannot reject draft in status: {draft.status}")

    resolved = await ApprovalRegistry.resolve_approval(
        approval_id=draft_id,
        decision="deny",
        edited_payload={"growth_status": "REJECTED"},
    )
    if resolved is None:
        raise HTTPException(status_code=404, detail="Draft not found")

    rejected_draft = _to_skill_draft_record(resolved)
    await record_skill_growth_event(
        entity_id=rejected_draft.id,
        draft_type=rejected_draft.draft_type,
        status="REJECTED",
        skill_name=rejected_draft.name,
        summary=rejected_draft.description or rejected_draft.name or rejected_draft.draft_type,
        detail={"approval_status": rejected_draft.approval_status},
    )
    _publish_draft_event(rejected_draft)

    return {"id": draft_id, "status": "REJECTED"}
