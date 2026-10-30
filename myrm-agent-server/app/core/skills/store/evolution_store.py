"""Shared evolution SkillStore accessor for core and API layers.

[INPUT]
- app.config.settings::settings (POS: 统一配置中心)
- app.core.skills.models::Skill (POS: 技能统一模型)
- myrm_agent_harness.agent.skills.evolution::SkillStore, SkillRecord (POS: harness 进化存储)

[OUTPUT]
- get_evolution_skill_store: 返回 skills.db 上的进程级单例 SkillStore 实例
- find_evolution_records: 一个技能在进化库里的全部行（按引用精确匹配的行优先，其次存放同一 SKILL.md 目录的同名行）
- reset_evolution_skill_store: 清空单例缓存（测试隔离用）

[POS]
core/skills/store 进化 SQLite 入口。禁止 core/services 经 app.api 间接访问。
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from myrm_agent_harness.agent.skills.evolution import SkillRecord, SkillStore

if TYPE_CHECKING:
    from app.core.skills.models import Skill

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

    A skill's rows are not keyed alike (draft approval and auto extraction key by the skill name, batch import
    by a generated id), so the page's skill id alone can miss them. A row found by name counts only when it holds
    the skill's own SKILL.md, so two skills sharing a name never share a row. Without ``page_skill`` ``skill_ref``
    is taken as the name.
    """
    records: list[SkillRecord] = []
    exact = store.get_skill(skill_ref)
    if exact is not None:
        records.append(exact)
    by_name = store.get_skill_by_name_version(skill_ref if page_skill is None else page_skill.name)
    if by_name is not None and by_name.skill_id != skill_ref and _holds_skill_md(by_name, page_skill):
        records.append(by_name)
    return records


def _holds_skill_md(record: SkillRecord, page_skill: Skill | None) -> bool:
    if page_skill is None:
        return True
    return bool(record.path) and Path(record.path).parent.resolve() == Path(page_skill.storage_path).resolve()


def reset_evolution_skill_store() -> None:
    """Drop cached SkillStore instances (test isolation / config reload)."""
    _store_cache.clear()
