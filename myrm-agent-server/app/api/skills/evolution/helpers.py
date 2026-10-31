"""Evolution API helpers shared by router modules.

[INPUT]
- app.core.skills.store.evolution_store::get_evolution_skill_store, get_evolution_skill_store_db_path, find_evolution_records, evolution_record_for_page_skill (POS: core/skills/store 进化 SQLite 入口)
- app.core.skills.store.service::skills_service (POS: Skill 商店服务；页面 id、目录名或已知名字找本地页面技能)
- myrm_agent_harness.agent.skills.evolution::skill_from_disk (POS: 进化引擎所用的 SKILL.md 文本与进化锁)

[OUTPUT]
- _evolution_lineage_id: stable lineage key for evolution records
- _get_skill_store: SkillStore accessor for evolution API routes
- _get_skill_store_db_path: skills.db path for evolution flows
- _require_evolvable_record: evolution row a user-driven evolution runs on, found by row id, page id or the directory name or a known name of a local skill; a local skill without one gets a row, 404 for an unknown skill, 409 when locked, 422 when its SKILL.md is too large to store

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

    A local skill on the Skills page may have no row yet, so it is given one from the page skill, found by its page
    id or, as the growth audit names it, by the name of its directory or a name it is known by (the name in its
    SKILL.md, or the one the agent runtime lists it under). The engine drops a request for a locked skill
    after the endpoint has answered, so the lock is refused here, judged as the engine judges it (the row's flag or
    the lock in the skill's SKILL.md), and a locked skill gets no new row.
    """
    from app.core.skills.store.evolution_store import evolution_record_for_page_skill, find_evolution_records
    from app.core.skills.store.service import skills_service

    store = _get_skill_store()
    record = store.get_skill(skill_ref)
    is_new = False
    if record is None:
        page_skill = await skills_service.get_skill(skill_ref)
        records = find_evolution_records(store, skill_ref, page_skill)
        if not records and page_skill is None:
            skill_dir = await skills_service.find_local_skill_dir(skill_ref)
            page_skill = await skills_service.get_local_skill(skill_dir) if skill_dir is not None else None
            records = find_evolution_records(store, skill_ref, page_skill) if page_skill is not None else []
        record = records[0] if records else None
        if record is None and page_skill is not None:
            record = await evolution_record_for_page_skill(page_skill)
            is_new = record is not None
    if record is None:
        raise HTTPException(status_code=404, detail=f"Skill not found: {skill_ref}")
    if skill_from_disk(record).evolution_locked:
        raise HTTPException(
            status_code=409,
            detail=f"Skill '{record.name}' is locked from evolution. Unlock it on the Skills page first.",
        )
    if is_new:
        try:
            await store.save_skill(record)
        except ValueError as exc:  # SKILL.md is beyond the content size the store accepts
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    return record
