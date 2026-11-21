"""A multi-statement SkillStore write is one transaction: when a step raises, nothing of it is published by a later write."""

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.skills.evolution.core.types import EvolutionType, SkillLineage, SkillRecord
from myrm_agent_harness.agent.skills.evolution.db.store import SkillStore


class _StepFailedError(Exception):
    """A failure outside sqlite3, which ``db_retry`` lets through without a retry."""


def _record(skill_id: str) -> SkillRecord:
    return SkillRecord(
        skill_id=skill_id,
        name=skill_id,
        description=f"desc for {skill_id}",
        content=f"---\nname: {skill_id}\ndescription: ok\n---\nbody",
        path=f"skills/{skill_id}.md",
        lineage=SkillLineage(evolution_type=EvolutionType.CAPTURED, version=1),
    )


def _raise_step_failed(*_args: object) -> None:
    raise _StepFailedError


def _committed_skill_ids(db_path: Path) -> list[str]:
    """The skill ids a second connection sees, that is, what is committed."""
    observer = sqlite3.connect(db_path)
    try:
        return sorted(row[0] for row in observer.execute("SELECT skill_id FROM skills"))
    finally:
        observer.close()


@pytest.fixture
def store(tmp_path: Path) -> Iterator[SkillStore]:
    opened = SkillStore(db_path=tmp_path / "atomic.db")
    yield opened
    opened.close()


@pytest.mark.asyncio
async def test_a_failed_batch_save_leaves_no_row_for_a_later_write_to_publish(
    store: SkillStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SkillStore, "_sync_skills_dependencies_locked", _raise_step_failed)

    with pytest.raises(_StepFailedError):
        await store.save_skills_batch([_record("first"), _record("second")])
    await store.save_skill(_record("later"))

    assert _committed_skill_ids(store.db_path) == ["later"]


@pytest.mark.asyncio
async def test_a_failed_single_save_leaves_no_row_for_a_later_write_to_publish(
    store: SkillStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SkillStore, "_sync_skill_dependencies_locked", _raise_step_failed)

    with pytest.raises(_StepFailedError):
        await store.save_skill(_record("first"))
    await store.save_skills_batch([_record("later")])

    assert _committed_skill_ids(store.db_path) == ["later"]


@pytest.mark.asyncio
async def test_a_failed_delete_keeps_the_skill_through_a_later_write(
    store: SkillStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    await store.save_skill(_record("kept"))
    monkeypatch.setattr(SkillStore, "_delete_skill_dependencies_locked", _raise_step_failed)

    with pytest.raises(_StepFailedError):
        await store.delete_skill("kept")
    await store.save_skill(_record("later"))

    assert _committed_skill_ids(store.db_path) == ["kept", "later"]


@pytest.mark.asyncio
async def test_a_failed_write_does_not_leave_the_connection_inside_a_transaction(
    store: SkillStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(SkillStore, "_sync_skills_dependencies_locked", _raise_step_failed)

    with pytest.raises(_StepFailedError):
        await store.save_skills_batch([_record("first")])

    assert not store._conn.in_transaction
