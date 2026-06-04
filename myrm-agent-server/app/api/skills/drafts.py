from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from app.core.skills.config_version import bump_skill_config_version
from app.database.connection import get_session
from app.database.models import ApprovalRecord
from app.services.approvals.registry import ApprovalRegistry
from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus
from app.services.skills.evolution_events import publish_skill_evolved_event
from app.services.skills.experience_ledger import record_skill_growth_event

logger = logging.getLogger(__name__)
router = APIRouter()

_SKILL_DRAFT_ACTION_TYPES: tuple[str, ...] = ("skill_draft", "skill_patch", "semantic_memory")

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

    class Config:
        from_attributes = True

class SkillDraftListResponse(BaseModel):
    drafts: list[SkillDraftResponse]
    total: int

class ApproveDraftRequest(BaseModel):
    skill_name: str | None = None

@dataclass(slots=True)
class SkillDraftRecord:
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
    approval_status: str

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
    )

async def _get_approval_skill_draft(draft_id: str) -> ApprovalRecord | None:
    async with get_session() as db:
        result = await db.execute(
            select(ApprovalRecord).where(
                ApprovalRecord.id == draft_id,
                ApprovalRecord.action_type.in_(_SKILL_DRAFT_ACTION_TYPES),
            )
        )
        return result.scalar_one_or_none()

def _publish_skill_growth_event(draft: SkillDraftRecord) -> None:
    try:
        bus = get_event_bus()
        bus.publish(
            AppEvent(
                event_type=AppEventType.SKILL_GROWTH_UPDATED,
                data={
                    "case_id": draft.id,
                    "draft_type": draft.draft_type,
                    "status": draft.status,
                    "name": draft.name or draft.draft_type,
                },
            )
        )
    except Exception as exc:
        logger.error("Failed to publish skill growth event: %s", exc)


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
                ApprovalRecord.action_type.in_(_SKILL_DRAFT_ACTION_TYPES),
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
                ApprovalRecord.action_type.in_(_SKILL_DRAFT_ACTION_TYPES),
            )
        )
        count = sum(1 for record in result.scalars().all() if _approval_growth_status(record) == "PENDING_REVIEW")
    return {"unreviewed_count": count}

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
        mat_result = await _materialize_skill_draft(approved_draft, request.skill_name)
    elif approved_draft.draft_type == "skill_patch":
        mat_result = await _materialize_skill_patch(approved_draft)
    elif approved_draft.draft_type == "semantic_memory":
        mat_result = await _materialize_semantic_memory(approved_draft)
    else:
        mat_result = {}

    if mat_result and not mat_result.get("materialized"):
        await _rollback_draft_status(draft_id)
        pending_record = await _get_approval_skill_draft(draft_id)
        if pending_record is not None:
            _publish_skill_growth_event(_to_skill_draft_record(pending_record))
    else:
        await record_skill_growth_event(
            entity_id=approved_draft.id,
            draft_type=approved_draft.draft_type,
            status="APPROVED",
            skill_name=request.skill_name or approved_draft.name,
            summary=approved_draft.description or approved_draft.name or approved_draft.draft_type,
            detail={"approval_status": approved_draft.approval_status},
        )
        _publish_skill_growth_event(approved_draft)

        if approved_draft.draft_type in {"skill_draft", "skill_patch"} and approved_draft.name:
            publish_skill_evolved_event(
                skill_name=request.skill_name or approved_draft.name,
                evolution_type="new" if approved_draft.draft_type == "skill_draft" else "patch",
                description=approved_draft.description or approved_draft.name,
            )

    materialized.update(mat_result)
    return materialized

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

async def _materialize_skill_draft(
    draft: SkillDraftRecord,
    override_name: str | None,
) -> dict[str, str | bool | None]:
    """Write an approved skill draft to disk as a local SKILL.md and auto-enable."""
    from app.core.skills.creation.service import skill_creation_service

    raw_name = override_name or draft.name
    if not raw_name:
        logger.warning("Skill draft %s has no name, skipping materialization", draft.id)
        return {"materialized": False, "error": "Skill draft has no name"}

    skill_name = _slugify_skill_name(raw_name)

    skill_md = _build_skill_md(skill_name, draft.description, draft.trigger_condition, draft.skill_steps)
    save_result = await skill_creation_service.save_skill(
        name=skill_name,
        content=skill_md,
        description=draft.description or "",
    )

    if save_result.success:
        bump_skill_config_version()
        logger.info("Skill draft materialized: %s -> %s", draft.id, save_result.skill_id)
        return {
            "materialized": True,
            "materialized_type": "skill",
            "skill_id": save_result.skill_id,
            "skill_name": save_result.skill_name,
            "saved_path": save_result.saved_path,
        }

    logger.warning("Skill draft materialization failed: %s - %s", draft.id, save_result.error)
    return {"materialized": False, "error": save_result.error}

async def _materialize_skill_patch(draft: SkillDraftRecord) -> dict[str, str | bool | None]:
    """Apply an approved skill patch to an existing skill."""
    from app.core.skills.creation.service import skill_creation_service
    from app.core.skills.store.service import skills_service

    skill_name = draft.name
    if not skill_name:
        return {"materialized": False, "error": "Skill patch has no name"}

    # patch target is a local skill
    from app.core.skills.providers.local import compute_local_skill_id

    skill_id = compute_local_skill_id(skill_creation_service.base_path / skill_name)
    skill = await skills_service.get_skill(skill_id)
    if not skill:
        logger.warning("Skill patch target not found: %s", skill_id)
        return {"materialized": False, "error": f"Target skill not found: {skill_id}"}

    skill_content_bytes = await skills_service.get_skill_file(skill_id, "SKILL.md")
    if not skill_content_bytes:
        return {"materialized": False, "error": "Could not read original SKILL.md"}

    original_content = skill_content_bytes.decode("utf-8") if isinstance(skill_content_bytes, bytes) else skill_content_bytes

    patch_content = draft.content or ""

    from myrm_agent_harness.utils.fuzzy_match import fuzzy_replace

    pattern = r"<<<<<<<\s*SEARCH\n(.*?)\n=======\n(.*?)\n>>>>>>>\s*REPLACE"
    blocks = re.findall(pattern, patch_content, flags=re.DOTALL)

    new_content = original_content
    if not blocks:
        # Fallback: maybe the LLM just returned the full new markdown instead of a diff?
        if patch_content.startswith("---"):
            new_content = patch_content
        else:
            return {"materialized": False, "error": "No valid SEARCH/REPLACE blocks found in patch"}
    else:
        for search, replace in blocks:
            replace_result = fuzzy_replace(new_content, search, replace, replace_all=False)
            if replace_result.success:
                new_content = replace_result.content
            else:
                logger.warning("Fuzzy replace failed for block: %s", search[:50])
                return {"materialized": False, "error": f"SEARCH block not found or ambiguous: {search[:50]}..."}

    save_result = await skill_creation_service.save_skill(
        name=skill_name,
        content=new_content,
        description=skill.description or "",
    )

    if save_result.success:
        bump_skill_config_version()
        logger.info("Skill patch materialized: %s -> %s", draft.id, save_result.skill_id)
        return {
            "materialized": True,
            "materialized_type": "skill_patch",
            "skill_id": save_result.skill_id,
            "skill_name": save_result.skill_name,
            "saved_path": save_result.saved_path,
        }

    return {"materialized": False, "error": save_result.error}

async def _materialize_semantic_memory(draft: SkillDraftRecord) -> dict[str, str | bool | None]:
    """Write an approved semantic memory draft into the memory store."""
    content = draft.content or ""
    if not content:
        return {"materialized": False, "error": "Draft has no content"}

    try:
        from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
        from app.services.agent.platform_config import require_platform_embedding_config

        embedding_cfg = await require_platform_embedding_config()

        manager = await create_memory_manager(
            resolve_context_binding(
                namespaces=None,
                agent_id=None,
                channel_id=None,
                conversation_id=None,
                task_id=None,
            ),
            embedding_config=embedding_cfg,
            approval_required=False,
        )
        memory = await manager.add_knowledge(content, importance=0.6, tags=["auto-review"])
        logger.info("Semantic memory materialized from draft %s: id=%s", draft.id, memory.id)
        return {
            "materialized": True,
            "materialized_type": "memory",
            "memory_id": str(memory.id),
        }
    except Exception as e:
        logger.error("Failed to materialize semantic memory from draft %s: %s", draft.id, e)
        return {"materialized": False, "error": str(e)}

def _slugify_skill_name(raw: str) -> str:
    """Convert a human-readable skill name to a valid slug (a-zA-Z0-9_-)."""
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", raw.strip())
    slug = slug.strip("-")
    return slug[:64] or "auto-skill"

def _build_skill_md(
    name: str,
    description: str | None,
    trigger_condition: str | None,
    skill_steps: str | None,
) -> str:
    """Build a minimal SKILL.md with YAML frontmatter from draft fields."""
    desc = (description or name).replace('"', '\\"')
    lines = [
        "---",
        f"name: {name}",
        f'description: "{desc}"',
        "---",
        "",
    ]
    if trigger_condition:
        lines.append(f"## When to Use\n{trigger_condition}\n")
    if skill_steps:
        lines.append(f"## Steps\n{skill_steps}\n")
    return "\n".join(lines)

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
    _publish_skill_growth_event(rejected_draft)

    return {"id": draft_id, "status": "REJECTED"}

