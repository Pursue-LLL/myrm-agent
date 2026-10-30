"""Evolution API helpers shared by router modules.

[INPUT]
- app.core.skills.store.evolution_store::get_evolution_skill_store, get_evolution_skill_store_db_path, find_evolution_records (POS: core/skills/store 进化 SQLite 入口)
- app.core.skills.store.service::skills_service (POS: Skill 商店服务)
- myrm_agent_harness.agent.skills.evolution::skill_from_disk (POS: 进化引擎所用的 SKILL.md 文本与进化锁)

[OUTPUT]
- _evolution_lineage_id: stable lineage key for evolution records
- _get_skill_store: SkillStore accessor for evolution API routes
- _get_skill_store_db_path: skills.db path for evolution flows
- _require_evolvable_record: evolution row a user-driven evolution runs on; 404 without a row, 409 when locked

[POS]
Thin API-layer helpers for evolution routers. Delegates storage to core; no business logic.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from myrm_agent_harness.agent.skills.evolution import SkillRecord, SkillStore, skill_from_disk


def _evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"


def _get_skill_store() -> SkillStore:
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    return get_evolution_skill_store()


def _get_skill_store_db_path() -> Path:
    from app.core.skills.store.evolution_store import get_evolution_skill_store_db_path

    return get_evolution_skill_store_db_path()


async def _require_evolvable_record(skill_ref: str) -> SkillRecord:
    """The evolution row of a skill named by page id, row id or name, once it may be evolved.

    The engine drops a request for a locked skill after the endpoint has answered, so the lock is refused here,
    judged as the engine judges it: the row's flag or the lock in the skill's SKILL.md.
    """
    from app.core.skills.store.evolution_store import find_evolution_records
    from app.core.skills.store.service import skills_service

    store = _get_skill_store()
    record = store.get_skill(skill_ref)
    if record is None:
        records = find_evolution_records(store, skill_ref, await skills_service.get_skill(skill_ref))
        record = records[0] if records else None
    if record is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_ref}")
    if skill_from_disk(record).evolution_locked:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{record.name}' is locked from evolution. Unlock it on the Skills page first.",
        )
    return record
