"""Shared evolution SkillStore accessor for core and API layers.

[INPUT]
- app.config.settings::settings (POS: 统一配置中心)
- myrm_agent_harness.agent.skills.evolution::SkillStore (POS: harness 进化存储)

[OUTPUT]
- get_evolution_skill_store: 返回 skills.db 上的 SkillStore 实例

[POS]
core/skills/store 进化 SQLite 入口。禁止 core/services 经 app.api 间接访问。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore


def get_evolution_skill_store_db_path() -> Path:
    """Resolve the unified skill-store SQLite path for evolution flows."""
    from app.config.settings import settings

    return Path(settings.database.state_dir) / "skills.db"


def get_evolution_skill_store() -> SkillStore:
    """Get or create the shared evolution SkillStore instance."""
    return SkillStore(db_path=get_evolution_skill_store_db_path())
