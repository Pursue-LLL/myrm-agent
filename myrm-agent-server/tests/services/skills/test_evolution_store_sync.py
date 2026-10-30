"""The evolution store's copy of a skill follows its SKILL.md: what is compared, what is copied, what is left alone."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.agent.skills.evolution import SkillStore
from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord

from app.services.skills.evolution_review.disk_content import skill_file_differs, sync_store_from_disk

_STORED = "---\nname: demo-skill\ndescription: As the store has it.\n---\n"
_ON_DISK = "---\nname: demo-skill\ndescription: As the user edited it.\nevolution-locked: true\n---\n"
_LAST_EVOLVED = datetime(2026, 1, 1, 12, 0, 0)


def _record(skill_path: Path | str) -> SkillRecord:
    return SkillRecord(
        skill_id="skill-1",
        name="demo-skill",
        description="Demo.",
        content=_STORED,
        path=str(skill_path),
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED),
        updated_at=_LAST_EVOLVED,
        evolution_locked=True,
        eval_cases=[{"input": "x"}],
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


@pytest.mark.asyncio
async def test_sync_copies_the_file_into_the_store_and_leaves_the_rest_of_the_record(store: SkillStore, skill_file: Path) -> None:
    await store.save_skill(_record(skill_file))
    stored = store.get_skill("skill-1")
    assert stored is not None

    assert await sync_store_from_disk(store, stored) is True

    refreshed = store.get_skill("skill-1")
    assert refreshed is not None
    assert refreshed.content == _ON_DISK
    # The evolution cooldown counts from the last evolution, which copying a file is not.
    assert refreshed.updated_at == _LAST_EVOLVED
    assert refreshed.evolution_locked is True
    assert refreshed.eval_cases == [{"input": "x"}]


@pytest.mark.asyncio
async def test_sync_leaves_a_store_that_already_holds_the_file(tmp_path: Path) -> None:
    skill_file = tmp_path / "SKILL.md"
    skill_file.write_bytes(_STORED.replace("\n", "\r\n").encode("utf-8"))
    store = MagicMock()
    store.save_skill = AsyncMock()

    assert await sync_store_from_disk(store, _record(skill_file)) is False

    store.save_skill.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_skips_a_skill_whose_file_cannot_be_read(tmp_path: Path) -> None:
    store = MagicMock()
    store.save_skill = AsyncMock()

    assert await sync_store_from_disk(store, _record(tmp_path / "missing" / "SKILL.md")) is False
    assert await sync_store_from_disk(store, _record(tmp_path)) is False

    store.save_skill.assert_not_awaited()


@pytest.mark.asyncio
async def test_sync_reports_a_file_the_store_cannot_hold_without_storing_it(store: SkillStore, skill_file: Path) -> None:
    skill_file.write_text(_ON_DISK + "x" * SkillStore.MAX_SKILL_CONTENT_CHARS, encoding="utf-8")
    await store.save_skill(_record(skill_file))
    stored = store.get_skill("skill-1")
    assert stored is not None

    assert await sync_store_from_disk(store, stored) is True

    unchanged = store.get_skill("skill-1")
    assert unchanged is not None
    assert unchanged.content == _STORED
    assert stored.content == _STORED


@pytest.mark.parametrize(
    ("content", "expected"),
    [
        (_ON_DISK, False),
        (_ON_DISK.replace("\n", "\r\n"), False),
        (_STORED, True),
    ],
)
def test_file_differs_compares_the_text_ignoring_line_endings(skill_file: Path, content: str, expected: bool) -> None:
    assert skill_file_differs(str(skill_file), content) is expected


def test_file_differs_is_false_where_there_is_no_file_to_compare(tmp_path: Path) -> None:
    assert skill_file_differs("", _STORED) is False
    assert skill_file_differs(str(tmp_path / "missing" / "SKILL.md"), _STORED) is False
    assert skill_file_differs(str(tmp_path), _STORED) is False
