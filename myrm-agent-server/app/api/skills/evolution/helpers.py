from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore


def _evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"


def _get_skill_store_db_path() -> Path:
    """Resolve the unified skill-store SQLite path for evolution APIs."""
    from app.config.settings import settings

    return Path(settings.database.state_dir) / "skills.db"


def _get_skill_store() -> SkillStore:
    """Get or create the shared evolution SkillStore instance."""
    return SkillStore(db_path=_get_skill_store_db_path())
