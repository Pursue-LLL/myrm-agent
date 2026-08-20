"""[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: Harness 记忆底座管理器)
- app.services.memory.manager_deps::get_crud_memory_manager (POS: 记忆管理器依赖注入)
- app.core.skills.store.service::skills_service (POS: 技能存储管理服务)
- app.services.skills.growth.audit_queries::list_skill_growth_timeline (POS: 技能成长审计查询)

[OUTPUT]
- get_learning_timeline: 聚合全域记忆与技能成长时序流
- update_timeline_memory: 行内更新记忆并锁定用户校准
- archive_timeline_skill: 行内归档/启用技能
- delete_timeline_memory: 行内删除记忆

[POS]
统一学习时间线 API。汇聚 Agent 记忆沉淀与技能演化生命周期事件，提供游标分页与行内即时治理能力。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryType
from pydantic import BaseModel, Field

from app.core.skills.store.service import skills_service
from app.core.utils.errors import internal_error, not_found_error
from app.core.utils.response_utils import success_response
from app.services.memory.command_center.command_center import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud._common import _record_memory_event
from app.services.memory.operations.presentation import memory_to_item, parse_memory_type
from app.services.skills.growth.audit_queries import list_skill_growth_timeline

router = APIRouter()
logger = logging.getLogger(__name__)


class TimelineNodeKind(StrEnum):
    FACT_MEMORY = "fact_memory"
    PREFERENCE_MEMORY = "preference_memory"
    PROCEDURAL_MEMORY = "procedural_memory"
    EPISODIC_MEMORY = "episodic_memory"
    SKILL_EVOLUTION = "skill_evolution"
    SKILL_DRAFT = "skill_draft"


class LearningTimelineItem(BaseModel):
    id: str
    kind: TimelineNodeKind
    title: str
    content: str
    created_at: str
    agent_id: str | None = None
    confidence: float = 1.0
    importance: float = 0.5
    is_user_edited: bool = False
    source_chat_id: str | None = None
    status: str = "active"
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class LearningTimelineResponse(BaseModel):
    items: list[LearningTimelineItem]
    total_count: int
    has_more: bool
    next_cursor: str | None = None


class TimelineMemoryUpdateRequest(BaseModel):
    content: str | None = None
    importance: float | None = Field(default=None, ge=0.0, le=1.0)
    reasoning: str | None = None
    application: str | None = None
    tags: list[str] | None = None


class TimelineSkillArchiveResponse(BaseModel):
    skill_id: str
    is_active: bool
    message: str


@router.get("/learning-timeline")
async def get_learning_timeline(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    agent_id: str | None = Query(None, description="Filter by agent ID (or None for global)"),
    kind_filter: str | None = Query(None, description="Filter by node kind (comma separated)"),
    limit: int = Query(50, ge=1, le=100, description="Items per page limit"),
    cursor: str | None = Query(None, description="Timestamp cursor for pagination"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Fetch the unified learning timeline combining memory records and skill evolution events."""
    try:
        cutoff_dt = datetime.now(UTC) - timedelta(days=days)
        cursor_dt = datetime.fromisoformat(cursor) if cursor else None

        allowed_kinds = set(kind_filter.split(",")) if kind_filter else None

        items: list[LearningTimelineItem] = []

        # 1. Fetch memories
        memory_tasks = []
        for mem_type in ALL_MEMORY_TYPES:
            memory_tasks.append(
                manager.list_memories(
                    mem_type,
                    limit=limit * 2,
                    include_archived=False,
                    sort_by="created_at",
                    sort_order="desc",
                )
            )

        memory_results = await asyncio.gather(*memory_tasks, return_exceptions=True)

        for mem_type, mem_list in zip(ALL_MEMORY_TYPES, memory_results, strict=False):
            if isinstance(mem_list, Exception):
                logger.warning("Failed to list memories for %s: %s", mem_type, mem_list)
                continue

            for mem in mem_list:
                created_at = getattr(mem, "created_at", None) or getattr(mem, "timestamp", None)
                if not isinstance(created_at, datetime):
                    continue
                if created_at.tzinfo is None:
                    created_at = created_at.replace(tzinfo=UTC)

                if created_at < cutoff_dt:
                    continue
                if cursor_dt and created_at >= cursor_dt:
                    continue

                mem_scope_agent = getattr(getattr(mem, "scope", None), "agent_id", None)
                if agent_id and mem_scope_agent and mem_scope_agent != agent_id:
                    continue

                kind = TimelineNodeKind.FACT_MEMORY
                title = f"{mem_type.value.capitalize()} Memory"
                content_text = getattr(mem, "content", "")

                if mem_type == MemoryType.SEMANTIC:
                    if getattr(mem, "preference_type", None):
                        kind = TimelineNodeKind.PREFERENCE_MEMORY
                        title = "User Preference"
                    else:
                        kind = TimelineNodeKind.FACT_MEMORY
                        title = "Factual Knowledge"
                elif mem_type == MemoryType.PROCEDURAL:
                    kind = TimelineNodeKind.PROCEDURAL_MEMORY
                    trigger = getattr(mem, "trigger", "")
                    action = getattr(mem, "action", "")
                    title = f"Behavior Rule: {trigger[:30]}"
                    content_text = f"Trigger: {trigger}\nAction: {action}"
                elif mem_type == MemoryType.EPISODIC:
                    kind = TimelineNodeKind.EPISODIC_MEMORY
                    title = "Episodic Digest"

                if allowed_kinds and kind.value not in allowed_kinds:
                    continue

                is_user_locked = bool(getattr(mem, "is_user_locked", False))

                items.append(
                    LearningTimelineItem(
                        id=str(mem.id),
                        kind=kind,
                        title=title,
                        content=content_text,
                        created_at=created_at.isoformat(),
                        agent_id=mem_scope_agent,
                        confidence=float(getattr(mem, "confidence", 1.0) or 1.0),
                        importance=float(getattr(mem, "importance", 0.5) or 0.5),
                        is_user_edited=is_user_locked,
                        source_chat_id=getattr(mem, "source_chat_id", None),
                        status=getattr(mem, "status", "active"),
                        metadata={
                            "memory_type": mem_type.value,
                            "tags": ",".join(getattr(mem, "tags", []) or []),
                        },
                    )
                )

        # 2. Fetch skill evolution events
        try:
            timeline_events = await list_skill_growth_timeline(limit=limit * 2, days=days)
            for evt in timeline_events:
                evt_created = evt.created_at
                if evt_created.tzinfo is None:
                    evt_created = evt_created.replace(tzinfo=UTC)

                if evt_created < cutoff_dt:
                    continue
                if cursor_dt and evt_created >= cursor_dt:
                    continue

                kind = (
                    TimelineNodeKind.SKILL_DRAFT
                    if evt.source.value == "draft"
                    else TimelineNodeKind.SKILL_EVOLUTION
                )
                if allowed_kinds and kind.value not in allowed_kinds:
                    continue

                items.append(
                    LearningTimelineItem(
                        id=evt.case_id,
                        kind=kind,
                        title=f"Skill: {evt.skill_name}",
                        content=evt.change_summary or f"Evolution {evt.growth_type} ({evt.status.value})",
                        created_at=evt_created.isoformat(),
                        agent_id=None,
                        confidence=1.0,
                        importance=0.8,
                        status=evt.status.value,
                        metadata={
                            "skill_name": evt.skill_name,
                            "skill_id": evt.skill_id or "",
                            "growth_type": evt.growth_type,
                            "source": evt.source.value,
                        },
                    )
                )
        except Exception as exc:
            logger.warning("Failed to fetch skill evolution timeline: %s", exc)

        # 3. Sort all items descending by timestamp
        items.sort(key=lambda x: x.created_at, reverse=True)

        total_count = len(items)
        has_more = total_count > limit
        paginated_items = items[:limit]
        next_cursor = paginated_items[-1].created_at if has_more and paginated_items else None

        response_payload = LearningTimelineResponse(
            items=paginated_items,
            total_count=total_count,
            has_more=has_more,
            next_cursor=next_cursor,
        )
        return success_response(data=response_payload.model_dump())
    except Exception as e:
        raise internal_error(operation="Get learning timeline", exception=e) from e


@router.put("/learning-timeline/memory/{memory_type}/{memory_id}")
async def update_timeline_memory_item(
    memory_type: str,
    memory_id: str,
    body: TimelineMemoryUpdateRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Inline edit a memory node in the learning timeline, applying user lock."""
    mem_type = parse_memory_type(memory_type)
    try:
        updated = await manager.update_memory(
            memory_id,
            content=body.content,
            importance=body.importance,
            reasoning=body.reasoning,
            application=body.application,
            tags=body.tags,
            is_user_locked=True,
        )
        await _record_memory_event(
            kind=MemoryOperationKind.WRITE,
            summary="Timeline memory updated and locked manually.",
            memory_id=memory_id,
            memory_type=mem_type.value,
        )
        item = memory_to_item(updated, mem_type)
        return success_response(data=item.model_dump())
    except Exception as e:
        raise not_found_error("Memory", memory_id) from e


@router.delete("/learning-timeline/memory/{memory_id}")
async def delete_timeline_memory_item(
    memory_id: str,
    memory_type: str = Query(..., description="Memory type"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Inline delete a memory node from the learning timeline."""
    mem_type = parse_memory_type(memory_type)
    try:
        deleted = await manager.delete_memory(mem_type, memory_id)
        if not deleted:
            raise not_found_error("Memory", memory_id)
        await _record_memory_event(
            kind=MemoryOperationKind.DELETE,
            summary="Timeline memory deleted manually.",
            memory_id=memory_id,
            memory_type=mem_type.value,
        )
        return success_response(data={"deleted": True, "memory_id": memory_id})
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise not_found_error("Memory", memory_id) from e


@router.post("/learning-timeline/skill/{skill_id}/archive")
async def archive_timeline_skill_item(
    skill_id: str,
    active: bool = Query(False, description="Set active status (False for archive)"),
) -> JSONResponse:
    """Inline archive or toggle active status of a skill node."""
    try:
        updated = await skills_service.update_skill(skill_id, is_active=active)
        if not updated:
            raise not_found_error("Skill", skill_id)
        status_msg = "Skill enabled" if active else "Skill archived"
        return success_response(
            data=TimelineSkillArchiveResponse(
                skill_id=skill_id,
                is_active=bool(updated.is_active),
                message=status_msg,
            ).model_dump()
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise not_found_error("Skill", skill_id) from e
