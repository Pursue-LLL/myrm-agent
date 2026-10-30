"""The evolution engine works from the SKILL.md on disk, not from a store copy an edit left behind."""

import logging
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.agent.skills.evolution.core.engine import SkillEvolutionEngine
from myrm_agent_harness.agent.skills.evolution.core.skill_on_disk import skill_from_disk
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore
from myrm_agent_harness.api.skills import read_skill_md

_STORED = "---\nname: demo-skill\ndescription: As the store has it.\n---\n"
_ON_DISK = "---\nname: demo-skill\ndescription: As the user edited it.\nevolution-locked: true\n---\n"


def _record(skill_path: Path | str) -> SkillRecord:
    return SkillRecord(
        skill_id="skill-1",
        name="demo-skill",
        description="Demo.",
        content=_STORED,
        path=str(skill_path),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
    )


@pytest.fixture
def skill_file(tmp_path: Path) -> Path:
    path = tmp_path / "demo-skill" / "SKILL.md"
    path.parent.mkdir()
    path.write_text(_ON_DISK, encoding="utf-8")
    return path


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SkillStore]:
    skill_store = SkillStore(db_path=tmp_path / "skills.db")
    yield skill_store
    skill_store.close()


def test_the_skill_takes_the_text_of_its_file_and_the_stored_record_is_left_alone(skill_file: Path) -> None:
    stored = _record(skill_file)

    from_disk = skill_from_disk(stored)

    assert from_disk.content == _ON_DISK
    assert stored.content == _STORED
    assert (from_disk.skill_id, from_disk.path, from_disk.name) == (stored.skill_id, stored.path, stored.name)


def test_a_file_with_the_same_text_in_other_line_endings_leaves_the_skill_as_it_is(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_bytes(_STORED.replace("\n", "\r\n").encode("utf-8"))
    stored = _record(path)

    assert skill_from_disk(stored) is stored


def test_a_skill_without_a_readable_file_stays_as_stored(tmp_path: Path) -> None:
    for unreadable in ("", str(tmp_path / "missing" / "SKILL.md"), str(tmp_path), "bad\x00path"):
        stored = _record(unreadable)

        assert skill_from_disk(stored) is stored


def test_a_file_larger_than_the_store_takes_is_not_evolved_from(
    skill_file: Path, caplog: pytest.LogCaptureFixture
) -> None:
    skill_file.write_text(_ON_DISK + "x" * SkillStore.MAX_SKILL_CONTENT_CHARS, encoding="utf-8")
    stored = _record(skill_file)

    with caplog.at_level(logging.WARNING, logger="myrm_agent_harness.agent.skills.evolution.core.skill_on_disk"):
        assert skill_from_disk(stored) is stored

    assert "larger than the evolution store takes" in caplog.text


def test_undecodable_bytes_are_replaced_so_the_text_is_stable(tmp_path: Path) -> None:
    path = tmp_path / "SKILL.md"
    path.write_bytes(b"---\nname: demo-skill\n---\n\xff\xfe\n")

    first, second = read_skill_md(path), read_skill_md(path)

    assert first is not None
    assert "\ufffd" in first
    assert first == second


@pytest.mark.asyncio
async def test_fix_and_derive_hand_the_pipeline_the_text_of_the_file(store: SkillStore, skill_file: Path) -> None:
    await store.save_skill(_record(skill_file))
    engine = SkillEvolutionEngine(store=store, llm=MagicMock())
    generate = AsyncMock(return_value=[])
    engine._variant_generator.generate_variants = generate  # no variants: the engine stops right after the call

    await engine.fix_skill("skill-1", "it fails")
    await engine.derive_skill_simple("skill-1", "cover more cases")

    assert [call.kwargs["skill"].content for call in generate.await_args_list] == [_ON_DISK, _ON_DISK]
    stored = store.get_skill("skill-1")
    assert stored is not None
    assert stored.content == _STORED
