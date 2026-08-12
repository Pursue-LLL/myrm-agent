"""Dependency impact query helpers for skill management actions.

Centralizes access to the persistent skill dependency graph so the
review, disable, and uninstall flows can surface impacted dependents.

[INPUT]
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: 进化 SQLite 入口)
- myrm_agent_harness.agent.skills.evolution::SkillStore (POS: harness 进化存储)

[OUTPUT]
- get_dependents_for_skill: 返回依赖某技能的库内技能 ID 列表
- get_dependents_map: 批量查询多技能的依赖者映射

[POS]
core/skills 依赖影响面查询，供 API 层做删除/停用前校验与审核详情展示。
"""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


async def get_dependents_map(skill_ids: list[str]) -> dict[str, list[str]]:
    """Resolve in-library dependents for a batch of skill IDs.

    Returns an empty mapping on any store failure so management flows are
    never blocked by dependency bookkeeping problems.

    Args:
        skill_ids: Skill identifiers to inspect.

    Returns:
        Mapping of skill ID to dependent skill IDs (possibly empty).
    """
    if not skill_ids:
        return {}
    try:
        from app.core.skills.store.evolution_store import get_evolution_skill_store

        store = get_evolution_skill_store()
        return await asyncio.to_thread(store.get_dependents_map, skill_ids)
    except Exception as e:
        logger.warning("Failed to load impacted dependents for %s: %s", skill_ids, e)
        return {}


async def get_dependents_for_skill(skill_id: str) -> list[str]:
    """Return in-library skill IDs that depend on the given skill.

    Args:
        skill_id: Skill identifier to inspect.

    Returns:
        Dependent skill IDs (possibly empty).
    """
    return (await get_dependents_map([skill_id])).get(skill_id, [])
