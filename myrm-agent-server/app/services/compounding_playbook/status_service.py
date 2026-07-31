"""Lightweight MSC compounding playbook status aggregation.

[INPUT]
- MemoryManager (memory counts)
- CronManager (job counts + acceptance criteria)
- SkillsService (installed skill counts)
- Agent DB row (optional agent_id skill_configs)

[OUTPUT]
- build_compounding_status: four-row checklist snapshot for Settings UI

[POS]
Server-only business service. Avoids full command-center / growth snapshot builds.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.compounding_playbook import (
    CompoundingChecklistItem,
    CompoundingPlaybookStatusResponse,
)

logger = logging.getLogger(__name__)

USER_ID = "default"
_MEMORY_TYPES: tuple[MemoryType, ...] = (
    MemoryType.PROFILE,
    MemoryType.SEMANTIC,
    MemoryType.CLAIM,
)


async def _count_memory_baseline(memory_manager: MemoryManager) -> int:
    total = 0
    for mem_type in _MEMORY_TYPES:
        try:
            total += await memory_manager.count_memories(mem_type)
        except Exception as exc:
            logger.warning("Compounding status: memory count failed for %s: %s", mem_type, exc)
    return total


async def _count_agent_skills(agent_id: str | None, db: AsyncSession | None) -> int:
    if not agent_id or db is None:
        return 0
    try:
        from sqlalchemy import select

        from app.database.models.agent import Agent

        row = await db.scalar(select(Agent).where(Agent.id == agent_id))
        if row is None:
            return 0
        bound = len(row.skill_configs or {})
        if bound > 0:
            return bound
        skill_ids = row.skill_ids if isinstance(row.skill_ids, list) else []
        mounted = row.mounted_skill_ids if isinstance(row.mounted_skill_ids, list) else []
        return len(set([*skill_ids, *mounted]))
    except Exception as exc:
        logger.warning("Compounding status: agent skill count failed: %s", exc)
        return 0


async def _count_active_skills() -> int:
    try:
        from app.core.skills.store.service import skills_service

        skills = await skills_service.list_skills()
        return sum(1 for skill in skills if skill.is_active)
    except Exception as exc:
        logger.warning("Compounding status: skills list failed: %s", exc)
        return 0


async def _count_cron_jobs(cron_manager: CronManager) -> tuple[int, int]:
    try:
        jobs = await cron_manager.list_jobs(USER_ID)
        verify_count = sum(
            1
            for job in jobs
            if job.acceptance_criteria and len(job.acceptance_criteria) > 0
        )
        return len(jobs), verify_count
    except Exception as exc:
        logger.warning("Compounding status: cron list failed: %s", exc)
        return 0, 0


async def build_compounding_status(
    *,
    memory_manager: MemoryManager,
    cron_manager: CronManager,
    agent_id: str | None = None,
    db: AsyncSession | None = None,
) -> CompoundingPlaybookStatusResponse:
    """Build the four-row MSC compounding checklist snapshot."""
    memory_count = await _count_memory_baseline(memory_manager)
    skill_count = await _count_agent_skills(agent_id, db)
    if skill_count == 0:
        skill_count = await _count_active_skills()

    cron_count, verify_count = await _count_cron_jobs(cron_manager)

    items: list[CompoundingChecklistItem] = [
        CompoundingChecklistItem(
            id="memory",
            ready=memory_count > 0,
            count=memory_count,
            deep_link="/settings/memory",
        ),
        CompoundingChecklistItem(
            id="skills",
            ready=skill_count > 0,
            count=skill_count,
            deep_link="/settings/skills",
        ),
        CompoundingChecklistItem(
            id="cron",
            ready=cron_count > 0,
            count=cron_count,
            deep_link="/settings/cron",
        ),
        CompoundingChecklistItem(
            id="verify",
            ready=verify_count > 0,
            count=verify_count,
            deep_link="/settings/cron",
        ),
    ]
    ready_count = sum(1 for item in items if item.ready)
    return CompoundingPlaybookStatusResponse(
        agent_id=agent_id,
        items=items,
        ready_count=ready_count,
        total_count=len(items),
    )
