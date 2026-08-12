"""Shared evolution SkillStore accessor for core and API layers.

[INPUT]
- app.config.settings::settings (POS: 统一配置中心)
- myrm_agent_harness.agent.skills.evolution::SkillStore (POS: harness 进化存储)

[OUTPUT]
- get_evolution_skill_store: 返回 skills.db 上的进程级单例 SkillStore 实例
- reset_evolution_skill_store: 清空单例缓存（测试隔离用）

[POS]
core/skills/store 进化 SQLite 入口。禁止 core/services 经 app.api 间接访问。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore

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


def reset_evolution_skill_store() -> None:
    """Drop cached SkillStore instances (test isolation / config reload)."""
    _store_cache.clear()
