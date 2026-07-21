"""Evolution API helpers shared by router modules.

[INPUT]
- app.core.skills.store.evolution_store::get_evolution_skill_store (POS: core/skills/store 进化 SQLite 入口)
- app.core.skills.store.evolution_store::get_evolution_skill_store_db_path (POS: core/skills/store 进化 SQLite 入口)

[OUTPUT]
- _evolution_lineage_id: stable lineage key for evolution records
- _get_skill_store: SkillStore accessor for evolution API routes
- _get_skill_store_db_path: skills.db path for evolution flows

[POS]
Thin API-layer helpers for evolution routers. Delegates storage to core; no business logic.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.skills.evolution import SkillStore


def _evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"


def _get_skill_store() -> SkillStore:
    from app.core.skills.store.evolution_store import get_evolution_skill_store

    return get_evolution_skill_store()


def _get_skill_store_db_path() -> Path:
    from app.core.skills.store.evolution_store import get_evolution_skill_store_db_path

    return get_evolution_skill_store_db_path()
