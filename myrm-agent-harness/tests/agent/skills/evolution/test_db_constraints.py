"""SkillStore's evolution constraints: which skills may be given one."""

from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore


def _record(skill_id: str) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name=skill_id,
        description="A test skill",
        content="# body",
        path=f"skills/{skill_id}/SKILL.md",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, parent_id=None),
    )


@pytest.mark.asyncio
async def test_a_constraint_for_a_skill_without_a_row_is_skipped(tmp_path: Path):
    """A reason for a skill the store holds no row for has no engine run to read it, and must not fail the caller."""
    store = SkillStore(db_path=tmp_path / "skills.db")
    await store.save_skill(_record("saved"))

    await store.add_evolution_constraint("never_saved", "Must not use os.system")
    await store.add_evolution_constraint("saved", "Keep the headings")

    assert store.get_evolution_constraints("never_saved") == []
    assert store.get_evolution_constraints("saved") == ["Keep the headings"]

    store.close()
