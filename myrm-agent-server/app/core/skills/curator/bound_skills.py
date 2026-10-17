"""Skills that agent profiles, cron jobs and kanban tasks bind explicitly.

[INPUT]
- app.database.connection::get_session (POS: Database session)
- app.database.models::Agent, CronJobModel, KanbanTaskModel (POS: Agent profile, cron job and kanban task rows)
- myrm_agent_harness.toolkits.cron.types::JobStatus (POS: Cron job lifecycle status)
- myrm_agent_harness.toolkits.kanban.types::TaskStatus (POS: Kanban task lifecycle status)
- myrm_agent_harness.backends.skills.local_skill_id::local_skill_id_from_path (POS: Canonical local skill ID)
- myrm_agent_harness.backends.skills.types::SkillMetadata (POS: Skill metadata)

[OUTPUT]
- bound_skill_names: Names of the given skills that an agent profile, a live cron job or a kanban task that can still run binds

[POS]
Tells the Curator which skills automations depend on, so an unattended job, board task or slash
command never finds its skill archived just because nobody invoked it interactively for a while.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from pathlib import Path

from myrm_agent_harness.backends.skills.local_skill_id import local_skill_id_from_path
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.toolkits.cron.types import JobStatus
from myrm_agent_harness.toolkits.kanban.types import TaskStatus
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.connection import get_session
from app.database.models import Agent, CronJobModel, KanbanTaskModel

# A task that can never run again: ``move_task`` lets a terminal task move nowhere but ARCHIVED, and nothing
# reopens a completed or archived one. A failed task is not in this set: ``retry_failed_task`` re-queues it,
# and it then loads its skills once more.
_FINAL_TASK_STATUSES = (TaskStatus.COMPLETED, TaskStatus.ARCHIVED)


async def bound_skill_names(skills: Sequence[SkillMetadata]) -> frozenset[str]:
    """Return the names of ``skills`` that an agent profile, a live cron job or a kanban task refers to.

    Every agent counts, enabled or not: a disabled agent can be switched back on, and
    archiving its skills in the meantime would silently break it. A completed cron job
    can never fire again, so only active and paused jobs count. A kanban task counts until
    it is completed or archived: a failed task can be retried and then needs its skills again.

    Database errors propagate: callers must not archive while they cannot tell what is bound.
    """
    async with get_session() as session:
        bound = await _bound_skill_ids(session)
    if not bound:
        return frozenset()
    return frozenset(skill.name for skill in skills if not bound.isdisjoint(_skill_ids(skill)))


async def _bound_skill_ids(session: AsyncSession) -> set[str]:
    bound: set[str] = set()

    agent_rows = await session.execute(select(Agent.skill_ids, Agent.mounted_skill_ids, Agent.command_bindings))
    for skill_ids, mounted_skill_ids, command_bindings in agent_rows:
        bound.update(_id_strings(skill_ids))
        bound.update(_id_strings(mounted_skill_ids))
        for binding in command_bindings or []:
            if isinstance(binding, dict):
                bound.update(_id_strings(binding.get("skill_ids")))
                bound.update(_id_strings(binding.get("skill_id")))

    job_rows = await session.execute(select(CronJobModel.skill_ids).where(CronJobModel.status != JobStatus.COMPLETED))
    for (skill_ids,) in job_rows:
        bound.update(_id_strings(skill_ids))

    task_rows = await session.execute(
        select(KanbanTaskModel.extra_skill_ids_json).where(KanbanTaskModel.status.notin_(_FINAL_TASK_STATUSES))
    )
    for (skill_ids,) in task_rows:
        bound.update(_id_strings(skill_ids))

    return bound


def _id_strings(value: object) -> Iterator[str]:
    """Yield the non-blank string IDs of a stored JSON value (a list, or a lone legacy string)."""
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, str) and item.strip():
            yield item.strip()


def _skill_ids(skill: SkillMetadata) -> set[str]:
    """Every ID under which a profile may refer to this local skill.

    Canonical path-hash IDs are what the UI writes today; ``local::{name}`` and the bare
    name are the legacy forms ``normalize_local_skill_id`` still accepts.
    """
    ids = {skill.name, f"local::{skill.name}"}
    if skill.storage_path:
        ids.add(local_skill_id_from_path(Path(skill.storage_path)))
    return ids
