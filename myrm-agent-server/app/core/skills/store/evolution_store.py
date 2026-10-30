"""Shared evolution SkillStore accessor for core and API layers.

[INPUT]
- app.config.settings::settings (POS: 统一配置中心)
- app.core.skills.models::Skill (POS: 技能统一模型)
- app.core.storage.types::SkillType (POS: 技能存储类型)
- myrm_agent_harness.agent.skills.evolution::SkillStore, SkillRecord, SkillLineage, EvolutionType (POS: harness 进化存储)

[OUTPUT]
- get_evolution_skill_store: 返回 skills.db 上的进程级单例 SkillStore 实例
- find_evolution_records: 一个技能在进化库里的全部行（按引用精确匹配的行优先，其次存放同一 SKILL.md 目录的行，不看行的名字）
- evolution_record_for_page_skill: 没有进化行的本地页面技能的新行（以页面 id 为键，读自它的 SKILL.md；非本地技能或无 SKILL.md 返回 None）
- reset_evolution_skill_store: 清空单例缓存（测试隔离用）

[POS]
core/skills/store 进化 SQLite 入口。禁止 core/services 经 app.api 间接访问。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.evolution import EvolutionType, SkillLineage, SkillRecord, SkillStore

from app.core.storage.types import SkillType

if TYPE_CHECKING:
    from app.core.skills.models import Skill

_PAGE_ROW_CREATOR = "skills_page"

_store_cache: dict[str, SkillStore] = {}


def get_evolution_skill_store_db_path() -> Path:
    """Resolve the unified skill-store SQLite path for evolution flows."""
    from app.config.settings import settings

    return Path(settings.database.state_dir) / "skills.db"


def get_evolution_skill_store() -> SkillStore:
    """Return the process-shared evolution SkillStore instance.

    The instance is cached per DB path and reused across call sites so hot
    read paths avoid paying connection setup, DDL replay, and a WAL
    checkpoint on every request. If a caller closed the cached store, a fresh
    instance is created lazily.
    """
    db_path = get_evolution_skill_store_db_path()
    key = str(db_path)
    store = _store_cache.get(key)
    if store is None or store.closed:
        store = SkillStore(db_path=db_path)
        _store_cache[key] = store
    return store


def find_evolution_records(store: SkillStore, skill_ref: str, page_skill: Skill | None = None) -> list[SkillRecord]:
    """Evolution rows of one skill, the row keyed by ``skill_ref`` first.

    Rows are keyed by whoever wrote them (skill name, generated id, page id) and a skill's name can change, so a page
    skill's other rows are the ones that hold its own SKILL.md, whatever they are named: a renamed skill keeps its
    row and two skills sharing a name never share one. Without ``page_skill`` ``skill_ref`` is taken as the name.
    """
    records: list[SkillRecord] = []
    exact = store.get_skill(skill_ref)
    if exact is not None:
        records.append(exact)
    if page_skill is None:
        by_name = store.get_skill_by_name_version(skill_ref)
        if by_name is not None and by_name.skill_id != skill_ref:
            records.append(by_name)
        return records
    skill_dir = Path(page_skill.storage_path).resolve()
    records.extend(
        record for record in store.get_active_skills() if record.skill_id != skill_ref and _holds_skill_md(record, skill_dir)
    )
    return records


async def evolution_record_for_page_skill(page_skill: Skill) -> SkillRecord | None:
    """A new evolution row for a local skill the store has none for, keyed by the skill's page id.

    Skills made in chat, placed by hand, installed from the market or recorded in the browser never pass
    through a writer that adds a row, yet the Skills page offers them evolution. The caller saves the row once
    the skill is known to be unlocked. Skills that are not local, or whose SKILL.md is gone, have nothing to
    evolve and get ``None``.
    """
    if page_skill.type is not SkillType.LOCAL:
        return None
    skill_md = Path(page_skill.storage_path) / "SKILL.md"
    try:
        content = await asyncio.to_thread(skill_md.read_text, encoding="utf-8", errors="replace")
    except OSError:
        return None
    return SkillRecord(
        skill_id=page_skill.id,
        name=page_skill.name,
        description=page_skill.description,
        content=content,
        path=str(skill_md),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, created_by=_PAGE_ROW_CREATOR),
    )


def _holds_skill_md(record: SkillRecord, skill_dir: Path) -> bool:
    return bool(record.path) and Path(record.path).parent.resolve() == skill_dir


def reset_evolution_skill_store() -> None:
    """Drop cached SkillStore instances (test isolation / config reload)."""
    _store_cache.clear()
