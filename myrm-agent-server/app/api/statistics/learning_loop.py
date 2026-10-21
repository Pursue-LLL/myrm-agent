"""[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager, MemoryType (POS: Harness 记忆底座管理器与记忆类型)
- app.services.memory.manager_deps::get_crud_memory_manager (POS: 记忆管理器依赖注入)
- app.services.memory.command_center.command_center_memory_scan::ALL_MEMORY_TYPES (POS: 指挥中心与统计共用的记忆类型清单)
- app.services.skills.growth.queries::SkillGrowthDashboardStatsRead, summarize_skill_growth_dashboard_stats (POS: 技能成长看板计数，与成长页同源)
- myrm_agent_harness.agent.event_log::EventFilter, FileEventLogBackend (POS: 事件日志存储与查询过滤)

[OUTPUT]
- get_learning_loop_status: 五环真实计数 (GET /api/v1/statistics/learning-loop/status)

[POS]
闭环学习五环状态 API。每环只暴露能从真实来源读到的计数，不做派生估算、不返回综合评分；
某个来源读取失败时对应环返回 null，由前端呈现「暂不可用」，不用默认值伪装成就绪。
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable
from pathlib import Path
from typing import TypeVar

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from myrm_agent_harness.agent.event_log import EventFilter
from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models import Chat
from app.services.memory.command_center.command_center_memory_scan import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.skills.growth.queries import SkillGrowthDashboardStatsRead, summarize_skill_growth_dashboard_stats

router = APIRouter()
logger = logging.getLogger(__name__)

_T = TypeVar("_T")


# ── Response Data Contracts ──────────────────────────────────────────


class Ring1ReflectionStatus(BaseModel):
    """Ring 1: distinct sessions that ended within the lookback window (event log)."""

    sessions_in_window: int


class Ring2DistillationStatus(BaseModel):
    """Ring 2: all-time skill-growth cases and how many of them were applied automatically."""

    cases_total: int
    cases_auto_applied: int


class Ring3AdvancementStatus(BaseModel):
    """Ring 3: all-time skill-growth cases waiting for the user or stopped by the safety gate."""

    cases_pending_review: int
    cases_blocked: int


class Ring4ConsolidationStatus(BaseModel):
    """Ring 4: memories stored across every memory type."""

    total_memories: int


class Ring5ProfilingStatus(BaseModel):
    """Ring 5: conversations available for cross-session recall and stored profile memories."""

    conversations: int
    profile_entries: int


class LearningLoopFiveRingStatusResponse(BaseModel):
    """Five-ring status; a ring is ``None`` when one of its sources could not be read."""

    ring1_reflection: Ring1ReflectionStatus | None
    ring2_distillation: Ring2DistillationStatus | None
    ring3_advancement: Ring3AdvancementStatus | None
    ring4_consolidation: Ring4ConsolidationStatus | None
    ring5_profiling: Ring5ProfilingStatus | None


# ── Source Readers ───────────────────────────────────────────────────


async def _read_source(name: str, source: Awaitable[_T]) -> _T | None:
    """Await one source so that its failure only takes down the rings that depend on it."""
    try:
        return await source
    except Exception as e:
        logger.warning("Learning loop source %s is unavailable: %s", name, e)
        return None


async def _count_recent_sessions(days: int) -> int:
    """Count sessions with a ``session_end`` event in the window; a session ending on several days counts once."""
    events_dir = Path(settings.database.event_log_dir)
    if not events_dir.exists():
        return 0

    backend = FileEventLogBackend(log_dir=events_dir, session_id="default")
    ended_in_window = EventFilter(event_types=frozenset({"session_end"}), start_time=time.time() - days * 86400)
    session_ids = await backend.get_all_session_ids()
    events_per_session = await asyncio.gather(*(backend.get_events(sid, ended_in_window) for sid in session_ids))
    return sum(1 for events in events_per_session if events)


async def _count_conversations(db: AsyncSession) -> int:
    return (await db.execute(select(func.count(Chat.id)))).scalar_one()


async def _count_memories(memory_manager: MemoryManager | None) -> dict[str, int]:
    """Count every memory type; one unreadable type fails the whole read instead of understating the total."""
    if memory_manager is None:
        raise RuntimeError("Memory manager is not configured")
    return {memory_type.value: await memory_manager.count_memories(memory_type) for memory_type in ALL_MEMORY_TYPES}


def _assemble_status(
    *,
    sessions: int | None,
    growth: SkillGrowthDashboardStatsRead | None,
    memory_counts: dict[str, int] | None,
    conversations: int | None,
) -> LearningLoopFiveRingStatusResponse:
    """Build the rings; a ring whose source is unavailable (``None``) stays ``None``."""
    return LearningLoopFiveRingStatusResponse(
        ring1_reflection=Ring1ReflectionStatus(sessions_in_window=sessions) if sessions is not None else None,
        ring2_distillation=(
            Ring2DistillationStatus(cases_total=growth.total, cases_auto_applied=growth.auto_applied)
            if growth is not None
            else None
        ),
        ring3_advancement=(
            Ring3AdvancementStatus(cases_pending_review=growth.pending_review, cases_blocked=growth.blocked)
            if growth is not None
            else None
        ),
        ring4_consolidation=(
            Ring4ConsolidationStatus(total_memories=sum(memory_counts.values())) if memory_counts is not None else None
        ),
        ring5_profiling=(
            Ring5ProfilingStatus(
                conversations=conversations,
                profile_entries=memory_counts[MemoryType.PROFILE.value],
            )
            if conversations is not None and memory_counts is not None
            else None
        ),
    )


# ── Main API Route ───────────────────────────────────────────────────


@router.get(
    "/learning-loop/status",
    response_model=LearningLoopFiveRingStatusResponse,
    summary="Get Five-Ring Closed Learning Loop Status",
)
async def get_learning_loop_status(
    days: int = Query(30, ge=1, le=365, description="Lookback window in days for ring 1 sessions"),
    db: AsyncSession = Depends(get_db),
    memory_manager: MemoryManager | None = Depends(get_crud_memory_manager),
) -> JSONResponse:
    """Report the real counters behind the five learning rings.

    Ring 1: distinct sessions that ended in the lookback window (event log)
    Ring 2/3: all-time skill-growth cases, same source as the skill growth page
    Ring 4: memories across every memory type
    Ring 5: conversations and profile memories
    """
    sessions, growth, memory_counts, conversations = await asyncio.gather(
        _read_source("event-log sessions", _count_recent_sessions(days)),
        _read_source("skill growth stats", summarize_skill_growth_dashboard_stats()),
        _read_source("memory counts", _count_memories(memory_manager)),
        _read_source("conversations", _count_conversations(db)),
    )
    status = _assemble_status(
        sessions=sessions,
        growth=growth,
        memory_counts=memory_counts,
        conversations=conversations,
    )
    return success_response(status.model_dump())
