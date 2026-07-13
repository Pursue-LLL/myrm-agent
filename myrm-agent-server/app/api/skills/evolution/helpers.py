"""Evolution API helpers shared by router modules."""

from __future__ import annotations

from app.core.skills.store.evolution_store import (
    get_evolution_skill_store as _get_skill_store,
    get_evolution_skill_store_db_path as _get_skill_store_db_path,
)


def _evolution_lineage_id(evolution_id: str) -> str:
    return f"evolution:{evolution_id}"
