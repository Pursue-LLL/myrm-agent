"""Cron lifecycle of the per-agent ima sync job.

[INPUT]
- app.core.cron.adapters.setup::get_cron_manager (POS: entitlement-guarded cron manager)
- app.core.cron.adapters.wiki_router_job_runner::WIKI_IMA_SYNC_COMMAND (POS: router command id)

[OUTPUT]
- find_job / is_job_active / start_job / pause_job / resume_job / stop_all_jobs / trigger_if_active

[POS]
One INTERVAL router job per agent drives the lane: ``trigger_now`` starts a backfill immediately, each slice
re-arms itself through ``JobResult.retry_at``, and the interval then keeps the library incrementally in sync.
Pause / resume map to the cron manager so the user controls the same job the scheduler runs; disconnecting
removes every agent's job because the credentials they share are gone. A slice that fired for the job asks
``is_job_active`` before it starts, so a pause that landed in between is honoured.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.cron.types import CronJob, JobStatus, JobType, Schedule, ScheduleKind, SessionTarget

from app.core.cron.adapters.setup import get_cron_manager
from app.core.cron.adapters.wiki_router_job_runner import WIKI_IMA_SYNC_COMMAND
from app.services.wiki.agent_scope import normalize_agent_scope

_USER_ID = "default"
SYNC_INTERVAL_MS = 6 * 3600 * 1000
# A slice is time-boxed well below this; the headroom absorbs the last in-flight items.
JOB_TIMEOUT_S = 600
# (name, description). The description is the line the cron list shows under the name; the cron manager requires
# one for every non-shell job, and a router job never reaches a model, so it only describes the sync to the user.
_COPY = {
    "zh": ("ima 知识库同步", "定期把 ima 里的知识库和笔记导入 Wiki，保持更新"),
    "en": ("ima Knowledge Sync", "Imports your ima knowledge bases and notes into the wiki and keeps them up to date"),
}


async def find_job(agent_id: str | None) -> CronJob | None:
    scope = normalize_agent_scope(agent_id)
    for job in await get_cron_manager().list_jobs(_USER_ID):
        if job.command == WIKI_IMA_SYNC_COMMAND and normalize_agent_scope(job.agent_id) == scope:
            return job
    return None


async def is_job_active(agent_id: str | None) -> bool:
    """Whether the agent's sync job exists and is neither paused nor removed."""
    job = await find_job(agent_id)
    return job is not None and job.status == JobStatus.ACTIVE


async def start_job(agent_id: str | None, *, locale: str) -> None:
    """Create (or resume) the job and run it now. A cron refusal (slot limit, rejected definition) is a ``ValueError``."""
    manager = get_cron_manager()
    job = await find_job(agent_id)
    if job is None:
        name, description = _COPY["zh" if locale.lower().startswith("zh") else "en"]
        job = await manager.create_job(
            _USER_ID,
            name,
            JobType.ROUTER,
            Schedule(kind=ScheduleKind.INTERVAL, interval_ms=SYNC_INTERVAL_MS),
            agent_id=agent_id,
            prompt=description,
            command=WIKI_IMA_SYNC_COMMAND,
            timeout_seconds=JOB_TIMEOUT_S,
            deduplicate=True,
            run_retention_days=7,
            session_target=SessionTarget.ISOLATED,
        )
    elif job.status == JobStatus.PAUSED:
        await manager.resume_job(job.id, _USER_ID)
    await manager.trigger_now(job.id, _USER_ID)


async def pause_job(agent_id: str | None) -> bool:
    job = await find_job(agent_id)
    if job is None:
        return False
    await get_cron_manager().pause_job(job.id, _USER_ID)
    return True


async def resume_job(agent_id: str | None) -> bool:
    job = await find_job(agent_id)
    if job is None:
        return False
    manager = get_cron_manager()
    await manager.resume_job(job.id, _USER_ID)
    await manager.trigger_now(job.id, _USER_ID)
    return True


async def stop_all_jobs() -> int:
    manager = get_cron_manager()
    jobs = [job for job in await manager.list_jobs(_USER_ID) if job.command == WIKI_IMA_SYNC_COMMAND]
    deleted = [await manager.delete_job(job.id, _USER_ID) for job in jobs]
    return sum(1 for ok in deleted if ok)


async def trigger_if_active(agent_id: str | None) -> None:
    job = await find_job(agent_id)
    if job is not None and job.status == JobStatus.ACTIVE:
        await get_cron_manager().trigger_now(job.id, _USER_ID)
