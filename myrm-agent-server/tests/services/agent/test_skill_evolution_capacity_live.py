"""Capacity guard against real stores: freeing a skill's space resumes learning."""

import shutil
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
from myrm_agent_harness.agent.skills.evolution import (
    BudgetCheckResult,
    EvolutionType,
    SkillBudgetConfig,
    SkillBudgetGovernor,
    SkillLineage,
    SkillRecord,
)
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.backends.skills.stats_collector import SkillStatsCollector

from app.core.skills.curator import service as curator_service
from app.services.agent.evolution.engine import check_skill_budget_before_evolution

_STORE_GETTER = "app.core.skills.store.evolution_store.get_evolution_skill_store"
_CAP = 10


@pytest.fixture
def skills_root(tmp_path: Path) -> Iterator[Path]:
    root = tmp_path / "skills"
    root.mkdir()
    with (
        patch.object(curator_service, "DEFAULT_LOCAL_SKILL_PATHS", [str(root)]),
        patch.object(curator_service, "_stats_collector", SkillStatsCollector()),
    ):
        yield root


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SkillStore]:
    skill_store = SkillStore(tmp_path / "skills.db")
    with patch(_STORE_GETTER, return_value=skill_store):
        yield skill_store
    skill_store.close()


async def _install_skills(store: SkillStore, root: Path, count: int) -> None:
    """Install ``count`` skills the way evolution does: a skill directory plus an active store record."""
    for index in range(count):
        name = f"skill-{index}"
        skill_dir = root / name
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(f"---\nname: {name}\ndescription: demo\n---\n", encoding="utf-8")
        await store.save_skill(
            SkillRecord(
                skill_id=name,
                name=name,
                description="demo",
                content="# demo",
                path=str(skill_md),
                lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
            )
        )


def _check() -> BudgetCheckResult:
    return check_skill_budget_before_evolution(governor=SkillBudgetGovernor(SkillBudgetConfig(max_skill_count=_CAP)))


@pytest.mark.asyncio
async def test_deleting_skills_resumes_learning(store: SkillStore, skills_root: Path) -> None:
    await _install_skills(store, skills_root, _CAP + 2)
    assert _check().allowed is False

    for index in range(3):
        shutil.rmtree(skills_root / f"skill-{index}")

    result = _check()
    assert result.allowed is True
    assert result.current_count == _CAP + 2 - 3


@pytest.mark.asyncio
async def test_archiving_a_skill_resumes_learning_and_restoring_it_pauses_again(store: SkillStore, skills_root: Path) -> None:
    await _install_skills(store, skills_root, _CAP)
    assert _check().allowed is False

    curator_service.set_skill_archived("skill-0", archived=True)
    assert _check().allowed is True

    curator_service.set_skill_archived("skill-0", archived=False)
    assert _check().allowed is False
