"""Skills bound by agent profiles / cron jobs / kanban tasks are found through real DB rows and real skill dirs."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.local import LocalSkillBackend
from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.kanban.types import TaskStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.curator.bound_skills import bound_skill_names
from app.database.models import Agent, CronJobModel, KanbanBoardModel, KanbanTaskModel
from app.database.models.base import Base

_SCHEDULE = {"kind": "cron", "expr": "0 8 * * *"}

# A failed task is retryable (``POST /tasks/{id}/retry`` re-queues it), so it still binds its skills.
_RUNNABLE_TASK_STATUSES = ("triage", "backlog", "ready", "running", "blocked", "in_review", "failed")
_FINAL_TASK_STATUSES = ("completed", "archived")

_BINDING_COLUMNS = frozenset(
    {"agents.skill_ids", "agents.mounted_skill_ids", "cron_jobs.skill_ids", "kanban_tasks.extra_skill_ids"}
)
_NON_BINDING_COLUMNS = frozenset(
    {
        "agents.skill_configs",  # per-skill flags such as ``is_core``, applied to skills the agent already loads
        "chats.session_loaded_skill_names",  # a record of what one session loaded
        "batch_snapshots.skill_id",
        "batch_snapshots.skill_content_before",
        "batch_snapshots.skill_version_before",
        "batch_snapshots.skill_metadata",
        "skill_package_revisions.skill_id",
        "skill_package_revisions.skill_md",
        "skill_permission_grants.skill_id",
        "skill_permission_usage_logs.skill_id",
        "skill_versions.skill_id",
        "turn_capability_metric_events.selected_skill_count",
        "turn_capability_metric_events.effective_skill_count",
    }
)


@pytest.fixture
async def skills(tmp_path: Path) -> list[SkillMetadata]:
    root = tmp_path / "skills"
    for name in ("alpha", "beta", "gamma"):
        skill_dir = root / name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(f"---\nname: {name}\ndescription: Skill {name}\n---\nBody.\n", encoding="utf-8")
    return await LocalSkillBackend(root, use_snapshot=False).list_skills()


def _canonical_id(skills: list[SkillMetadata], name: str) -> str:
    skill = next(s for s in skills if s.name == name)
    assert skill.storage_path is not None
    return local_skill_id_from_path(Path(skill.storage_path))


def _agent(agent_id: str, **fields: object) -> Agent:
    return Agent(id=agent_id, name=agent_id, **fields)


def _job(job_id: str, status: str, skill_ids: list[str] | None) -> CronJobModel:
    return CronJobModel(id=job_id, name=job_id, job_type="agent", schedule=_SCHEDULE, status=status, skill_ids=skill_ids)


def _task(task_id: str, status: str, skill_ids: list[str] | None) -> KanbanTaskModel:
    return KanbanTaskModel(id=task_id, board_id="b1", title=task_id, status=status, extra_skill_ids_json=skill_ids)


@pytest.fixture
async def board(session: AsyncSession) -> None:
    session.add(KanbanBoardModel(id="b1", name="Board"))
    await session.commit()


async def test_nothing_bound_protects_nothing(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    assert await bound_skill_names(skills) == frozenset()


async def test_agent_canonical_skill_id_protects_the_skill(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add(_agent("a1", skill_ids=[_canonical_id(skills, "alpha")]))
    await session.commit()

    assert await bound_skill_names(skills) == {"alpha"}


async def test_agent_legacy_local_name_id_protects_the_skill(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add(_agent("a1", skill_ids=["local::beta"]))
    await session.commit()

    assert await bound_skill_names(skills) == {"beta"}


async def test_agent_mounted_skill_ids_protect(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add(_agent("a1", skill_ids=[], mounted_skill_ids=[_canonical_id(skills, "gamma")]))
    await session.commit()

    assert await bound_skill_names(skills) == {"gamma"}


async def test_disabled_agent_still_protects(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add(_agent("a1", skill_ids=[_canonical_id(skills, "alpha")], is_active=False))
    await session.commit()

    assert await bound_skill_names(skills) == {"alpha"}


async def test_command_bindings_protect_current_and_legacy_shapes(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    bindings = [
        {"command_name": "daily", "skill_ids": [_canonical_id(skills, "alpha")]},
        {"command_name": "weekly", "skill_id": _canonical_id(skills, "beta")},
        {"command_name": "empty", "skill_ids": []},
    ]
    session.add(_agent("a1", skill_ids=[], command_bindings=bindings))
    await session.commit()

    assert await bound_skill_names(skills) == {"alpha", "beta"}


@pytest.mark.parametrize("status", ["active", "paused"])
async def test_live_cron_job_protects_its_skills(session: AsyncSession, skills: list[SkillMetadata], status: str) -> None:
    session.add(_job("j1", status, [_canonical_id(skills, "beta")]))
    await session.commit()

    assert await bound_skill_names(skills) == {"beta"}


async def test_completed_cron_job_does_not_protect(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add(_job("j1", "completed", [_canonical_id(skills, "beta")]))
    await session.commit()

    assert await bound_skill_names(skills) == frozenset()


async def test_cron_job_without_skills_and_blank_ids_are_ignored(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add_all([_job("j1", "active", None), _job("j2", "active", ["", "  "]), _agent("a1", skill_ids=["unknown-id"])])
    await session.commit()

    assert await bound_skill_names(skills) == frozenset()


@pytest.mark.usefixtures("board")
@pytest.mark.parametrize("status", _RUNNABLE_TASK_STATUSES)
async def test_kanban_task_that_can_still_run_protects_its_skills(
    session: AsyncSession, skills: list[SkillMetadata], status: str
) -> None:
    session.add(_task("t1", status, [_canonical_id(skills, "alpha")]))
    await session.commit()

    assert await bound_skill_names(skills) == {"alpha"}


@pytest.mark.usefixtures("board")
@pytest.mark.parametrize("status", _FINAL_TASK_STATUSES)
async def test_completed_or_archived_kanban_task_does_not_protect(
    session: AsyncSession, skills: list[SkillMetadata], status: str
) -> None:
    session.add(_task("t1", status, [_canonical_id(skills, "alpha")]))
    await session.commit()

    assert await bound_skill_names(skills) == frozenset()


def test_every_kanban_task_status_is_classified() -> None:
    """A new lifecycle state must be sorted into "can still run" or "final" here and in ``bound_skills``."""
    assert {status.value for status in TaskStatus} == {*_RUNNABLE_TASK_STATUSES, *_FINAL_TASK_STATUSES}


def test_every_skill_column_is_classified() -> None:
    """A new column whose name contains ``skill`` must be sorted into "automation binding" or "not a binding".

    A binding column has to be read by ``bound_skills`` (and covered by a test above); a column left out of it
    would let the Curator archive a skill that an unattended run still needs. Only the name is matched: a binding
    column without the word (``agents.command_bindings``) is invisible here and has to be added to ``bound_skills`` by hand.
    """
    columns = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if "skill" in column.name
    }

    assert columns == _BINDING_COLUMNS | _NON_BINDING_COLUMNS


@pytest.mark.usefixtures("board")
async def test_kanban_task_and_cron_job_protect_together(session: AsyncSession, skills: list[SkillMetadata]) -> None:
    session.add_all(
        [_task("t1", "ready", [_canonical_id(skills, "alpha")]), _job("j1", "active", [_canonical_id(skills, "beta")])]
    )
    await session.commit()

    assert await bound_skill_names(skills) == {"alpha", "beta"}


@pytest.mark.usefixtures("board")
async def test_kanban_task_legacy_ids_protect_and_blank_ids_are_ignored(
    session: AsyncSession, skills: list[SkillMetadata]
) -> None:
    session.add_all([_task("t1", "ready", ["local::gamma"]), _task("t2", "ready", None), _task("t3", "ready", ["", "  "])])
    await session.commit()

    assert await bound_skill_names(skills) == {"gamma"}
