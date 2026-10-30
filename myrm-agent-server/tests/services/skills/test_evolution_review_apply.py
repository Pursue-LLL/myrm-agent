"""apply_content_update: the evolution type is validated before anything is written."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillRecord

from app.services.skills.evolution_review.disk_content import apply_content_update
from app.services.skills.evolution_review.types import EvolutionApplyError, EvolutionApprovalPayload

_RETIRED_TYPE = "optimize_description"


def _payload(skill_file: Path, evolution_type: str) -> EvolutionApprovalPayload:
    return EvolutionApprovalPayload(
        skill_id="skill-1",
        skill_name="demo-skill",
        skill_path=str(skill_file),
        evolution_type=evolution_type,
        reason="apply test",
        original_content="original",
        evolved_content="evolved",
        confidence=0.9,
        test_passed=True,
    )


def _store() -> MagicMock:
    store = MagicMock()
    store.get_skill.return_value = None
    store.save_skill = AsyncMock()
    return store


@pytest.fixture
def skill_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text("original", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _snapshot_persistence() -> Iterator[None]:
    """The version-snapshot service needs the database; it is not what these tests exercise."""
    with ExitStack() as stack:
        for name in ("persist_skill_md_snapshot", "restore_skill_md_from_active_version"):
            stack.enter_context(patch(f"app.services.skills.write_orchestrator.{name}", new=AsyncMock()))
        yield


@pytest.mark.asyncio
@pytest.mark.parametrize("evolution_type", [EvolutionType.FIX, EvolutionType.DERIVED, EvolutionType.CAPTURED])
async def test_applying_a_supported_type_writes_the_evolved_content(skill_file: Path, evolution_type: EvolutionType) -> None:
    store = _store()

    await apply_content_update(_payload(skill_file, evolution_type.value), store)

    assert skill_file.read_text(encoding="utf-8") == "evolved"
    saved: SkillRecord = store.save_skill.await_args.args[0]
    assert saved.lineage.evolution_type is evolution_type


@pytest.mark.asyncio
async def test_applying_a_retired_type_is_refused_before_the_skill_file_is_touched(skill_file: Path) -> None:
    store = _store()

    with pytest.raises(EvolutionApplyError, match=_RETIRED_TYPE):
        await apply_content_update(_payload(skill_file, _RETIRED_TYPE), store)

    assert skill_file.read_text(encoding="utf-8") == "original"
    assert list(skill_file.parent.iterdir()) == [skill_file]
    store.save_skill.assert_not_awaited()
