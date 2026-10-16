"""[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: Harness 记忆底座管理器)
- app.services.memory.manager_deps::get_crud_memory_manager (POS: 记忆管理器依赖注入)
- app.services.memory.operations.crud.item_mutations::update_memory_item, delete_memory_item (POS: 记忆单条变更唯一实现)
- app.core.skills.curator.service::set_skill_archived, describe_skill_lifecycle (POS: 技能生命周期归档唯一入口)
- app.services.skills.growth.audit_queries::list_skill_growth_timeline (POS: 技能成长审计查询)

[OUTPUT]
- get_learning_timeline: 聚合全域记忆与技能成长时序流
- update_timeline_memory_item: 行内更新记忆并锁定用户校准
- delete_timeline_memory_item: 行内删除记忆（软删除，可由回收站恢复）
- archive_timeline_skill_item: 行内归档/恢复技能

[POS]
统一学习时间线 API。汇聚 Agent 记忆沉淀与技能演化生命周期事件，提供稳定游标分页与行内即时治理能力。
变更语义全部委托给记忆中心 / 技能策展的同一实现，本模块只负责时间线聚合与协议适配。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from pydantic import BaseModel, Field

from app.core.skills.curator.service import (
    SkillNotFoundError,
    SkillPinnedError,
    describe_skill_lifecycle,
    set_skill_archived,
)
from app.core.utils.errors import conflict_error, not_found_error, validation_error
from app.core.utils.response_utils import success_response
from app.schemas.memory.crud import UpdateMemoryRequest
from app.services.memory.command_center.command_center_memory_scan import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud.item_mutations import delete_memory_item, update_memory_item
from app.services.memory.operations.presentation import parse_memory_type
from app.services.skills.growth.audit_queries import list_skill_growth_timeline

router = APIRouter()
logger = logging.getLogger(__name__)

# Upper bound of rows pulled per source before merging. Filters (agent, time window,
# cursor) run on the full pulled set so pagination and total_count stay consistent.
_SOURCE_FETCH_CAP = 500
_CURSOR_SEPARATOR = "|"


class TimelineNodeKind(StrEnum):
    FACT_MEMORY = "fact_memory"
    PREFERENCE_MEMORY = "preference_memory"
    PROCEDURAL_MEMORY = "procedural_memory"
    EPISODIC_MEMORY = "episodic_memory"
    SKILL_EVOLUTION = "skill_evolution"
    SKILL_DRAFT = "skill_draft"


_MEMORY_TYPES_BY_KIND: dict[TimelineNodeKind, MemoryType] = {
    TimelineNodeKind.FACT_MEMORY: MemoryType.SEMANTIC,
    TimelineNodeKind.PREFERENCE_MEMORY: MemoryType.SEMANTIC,
    TimelineNodeKind.PROCEDURAL_MEMORY: MemoryType.PROCEDURAL,
    TimelineNodeKind.EPISODIC_MEMORY: MemoryType.EPISODIC,
}
_SKILL_KINDS = frozenset({TimelineNodeKind.SKILL_EVOLUTION, TimelineNodeKind.SKILL_DRAFT})


class LearningTimelineItem(BaseModel):
    id: str
    kind: TimelineNodeKind
    title: str
    content: str
    created_at: str
    agent_id: str | None = None
    confidence: float = 1.0
    importance: float = 0.5
    is_user_protected: bool = False
    source_chat_id: str | None = None
    status: str = "active"
    metadata: dict[str, str | int | float | bool] = Field(default_factory=dict)


class LearningTimelineResponse(BaseModel):
    items: list[LearningTimelineItem]
    total_count: int
    has_more: bool
    next_cursor: str | None = None


class TimelineSkillArchiveResponse(BaseModel):
    skill_name: str
    is_active: bool
    message: str


def _parse_kind_filter(raw: str | None) -> set[TimelineNodeKind] | None:
    if not raw:
        return None
    try:
        return {TimelineNodeKind(part.strip()) for part in raw.split(",") if part.strip()}
    except ValueError as exc:
        raise validation_error(f"Invalid kind_filter: {raw}") from exc


def _parse_cursor(raw: str | None) -> tuple[datetime, str] | None:
    """Cursor is ``<iso timestamp>|<item id>``; the id breaks ties between equal timestamps."""
    if not raw:
        return None
    timestamp, separator, item_id = raw.rpartition(_CURSOR_SEPARATOR)
    try:
        if not separator or not item_id:
            raise ValueError(raw)
        return _as_utc(datetime.fromisoformat(timestamp)), item_id
    except ValueError as exc:
        raise validation_error("Invalid cursor") from exc


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def _score_of(mem: object, field: str, default: float) -> float:
    """Read a 0-1 score; only a missing field falls back, so a real 0.0 is kept."""
    value = getattr(mem, field, None)
    return float(value) if isinstance(value, (int, float)) else default


def _is_user_protected(mem: object) -> bool:
    """Vector memories persist the user's protection as ``pinned``, procedural rules as ``is_user_locked``."""
    return bool(getattr(mem, "pinned", False) or getattr(mem, "is_user_locked", False))


def _memory_item(mem: object, mem_type: MemoryType, created_at: datetime) -> LearningTimelineItem:
    """Project a harness memory onto a timeline node; ``metadata.memory_type`` is the mutation key."""
    kind = TimelineNodeKind.FACT_MEMORY
    title = "Factual Knowledge"
    content = getattr(mem, "content", "")
    metadata_extra: dict[str, str] = {}

    if mem_type == MemoryType.SEMANTIC and getattr(mem, "preference_type", None):
        kind = TimelineNodeKind.PREFERENCE_MEMORY
        title = "User Preference"
    elif mem_type == MemoryType.PROCEDURAL:
        kind = TimelineNodeKind.PROCEDURAL_MEMORY
        title = str(getattr(mem, "trigger", ""))[:60]
        content = content or str(getattr(mem, "action", ""))
        metadata_extra["reasoning"] = str(getattr(mem, "reasoning", "") or "")
    elif mem_type == MemoryType.EPISODIC:
        kind = TimelineNodeKind.EPISODIC_MEMORY
        title = "Episodic Digest"

    return LearningTimelineItem(
        id=str(getattr(mem, "id", "")),
        kind=kind,
        title=title,
        content=content,
        created_at=created_at.isoformat(),
        agent_id=getattr(getattr(mem, "scope", None), "agent_id", None),
        confidence=_score_of(mem, "confidence", 1.0),
        importance=_score_of(mem, "importance", 0.5),
        is_user_protected=_is_user_protected(mem),
        source_chat_id=getattr(mem, "source_chat_id", None),
        status=str(getattr(mem, "status", "active")),
        metadata={
            "memory_type": mem_type.value,
            "tags": ",".join(getattr(mem, "tags", []) or []),
            **metadata_extra,
        },
    )


async def _collect_memory_nodes(
    manager: MemoryManager,
    memory_types: tuple[MemoryType, ...],
    agent_id: str | None,
) -> list[tuple[datetime, LearningTimelineItem]]:
    results = await asyncio.gather(
        *(
            manager.list_memories(
                mem_type,
                limit=_SOURCE_FETCH_CAP,
                include_archived=False,
                sort_by="created_at",
                sort_order="desc",
            )
            for mem_type in memory_types
        ),
        return_exceptions=True,
    )

    nodes: list[tuple[datetime, LearningTimelineItem]] = []
    for mem_type, memories in zip(memory_types, results, strict=True):
        if isinstance(memories, BaseException):
            logger.warning("Failed to list memories for %s: %s", mem_type, memories)
            continue
        for mem in memories:
            raw_created = getattr(mem, "created_at", None) or getattr(mem, "timestamp", None)
            if not isinstance(raw_created, datetime):
                continue
            scope_agent = getattr(getattr(mem, "scope", None), "agent_id", None)
            if agent_id and scope_agent and scope_agent != agent_id:
                continue
            created_at = _as_utc(raw_created)
            nodes.append((created_at, _memory_item(mem, mem_type, created_at)))
    return nodes


async def _collect_skill_nodes(days: int) -> list[tuple[datetime, LearningTimelineItem]]:
    try:
        events = await list_skill_growth_timeline(limit=_SOURCE_FETCH_CAP, days=days)
    except Exception as exc:
        logger.warning("Failed to fetch skill evolution timeline: %s", exc)
        return []

    lifecycle_by_skill = {name: describe_skill_lifecycle(name) for name in {evt.skill_name for evt in events if evt.skill_name}}

    nodes: list[tuple[datetime, LearningTimelineItem]] = []
    for evt in events:
        created_at = _as_utc(evt.created_at)
        kind = TimelineNodeKind.SKILL_DRAFT if evt.source.value == "draft" else TimelineNodeKind.SKILL_EVOLUTION
        lifecycle = lifecycle_by_skill.get(evt.skill_name)
        nodes.append(
            (
                created_at,
                LearningTimelineItem(
                    id=evt.case_id,
                    kind=kind,
                    title=evt.skill_name,
                    content=evt.change_summary,
                    created_at=created_at.isoformat(),
                    importance=0.8,
                    status=evt.status.value,
                    metadata={
                        "skill_name": evt.skill_name,
                        "skill_id": evt.skill_id or "",
                        "growth_type": evt.growth_type,
                        "source": evt.source.value,
                        "manageable": lifecycle is not None,
                        "archived": bool(lifecycle and lifecycle[0]),
                        "pinned": bool(lifecycle and lifecycle[1]),
                    },
                ),
            )
        )
    return nodes


@router.get("/learning-timeline")
async def get_learning_timeline(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days"),
    agent_id: str | None = Query(None, description="Filter by agent ID (or None for global)"),
    kind_filter: str | None = Query(None, description="Filter by node kind (comma separated)"),
    limit: int = Query(50, ge=1, le=100, description="Items per page limit"),
    cursor: str | None = Query(None, description="Opaque cursor returned by the previous page"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Fetch the unified learning timeline combining memory records and skill evolution events."""
    allowed_kinds = _parse_kind_filter(kind_filter)
    cursor_key = _parse_cursor(cursor)
    cutoff = datetime.now(UTC) - timedelta(days=days)

    memory_types = ALL_MEMORY_TYPES
    want_skills = True
    if allowed_kinds:
        memory_types = tuple(dict.fromkeys(_MEMORY_TYPES_BY_KIND[k] for k in allowed_kinds if k in _MEMORY_TYPES_BY_KIND))
        want_skills = bool(allowed_kinds & _SKILL_KINDS)

    sources = []
    if memory_types:
        sources.append(_collect_memory_nodes(manager, memory_types, agent_id))
    if want_skills:
        sources.append(_collect_skill_nodes(days))

    nodes = [node for source in await asyncio.gather(*sources) for node in source]
    nodes = [
        (created_at, item)
        for created_at, item in nodes
        if created_at >= cutoff
        and (not allowed_kinds or item.kind in allowed_kinds)
        and (cursor_key is None or (created_at, item.id) < cursor_key)
    ]
    nodes.sort(key=lambda node: (node[0], node[1].id), reverse=True)

    page = nodes[:limit]
    has_more = len(nodes) > limit
    next_cursor = f"{page[-1][1].created_at}{_CURSOR_SEPARATOR}{page[-1][1].id}" if has_more else None

    return success_response(
        data=LearningTimelineResponse(
            items=[item for _, item in page],
            total_count=len(nodes),
            has_more=has_more,
            next_cursor=next_cursor,
        ).model_dump()
    )


@router.put("/learning-timeline/memory/{memory_type}/{memory_id}")
async def update_timeline_memory_item(
    memory_type: str,
    memory_id: str,
    body: UpdateMemoryRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Inline edit a memory node. The edit is an explicit user lock: procedural rules are locked, other memories pinned."""
    item = await update_memory_item(
        manager,
        parse_memory_type(memory_type),
        memory_id,
        body.model_copy(update={"is_user_locked": True}),
    )
    return success_response(data=item.model_dump())


@router.delete("/learning-timeline/memory/{memory_id}")
async def delete_timeline_memory_item(
    memory_id: str,
    memory_type: str = Query(..., description="Memory type from the node's metadata.memory_type"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Inline delete a memory node; recoverable memories are archived exactly like the memory center."""
    deleted = await delete_memory_item(manager, parse_memory_type(memory_type), memory_id)
    return success_response(data=deleted)


@router.post("/learning-timeline/skill/{skill_name}/archive")
async def archive_timeline_skill_item(
    skill_name: str,
    active: bool = Query(False, description="True restores the skill, False archives it"),
) -> JSONResponse:
    """Inline archive or restore a skill through the curator lifecycle (pinned skills are refused)."""
    try:
        set_skill_archived(skill_name, archived=not active)
    except SkillNotFoundError as exc:
        raise not_found_error(f"Skill {skill_name}") from exc
    except SkillPinnedError as exc:
        raise conflict_error(f"Skill '{skill_name}' is pinned; unpin it before archiving") from exc

    return success_response(
        data=TimelineSkillArchiveResponse(
            skill_name=skill_name,
            is_active=active,
            message="Skill restored" if active else "Skill archived",
        ).model_dump()
    )
