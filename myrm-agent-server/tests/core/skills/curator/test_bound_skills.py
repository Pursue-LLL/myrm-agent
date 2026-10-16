"""Skills bound by agent profiles / cron jobs are found through real DB rows and real skill dirs."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.backends.skills.local import LocalSkillBackend
from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path
from myrm_agent_harness.backends.skills.types import SkillMetadata
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.skills.curator.bound_skills import bound_skill_names
from app.database.models import Agent, CronJobModel

_SCHEDULE = {"kind": "cron", "expr": "0 8 * * *"}


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
