"""[INPUT]
- .common (POS: shared constants and preset state)

[OUTPUT]
- _find_preset_cron_job, _find_read_it_later_cron_job, _find_wiki_morning_delta_cron_job, _find_wiki_maintain_cron_job, _ensure_blueprint_cron, _ensure_read_it_later_cron, _ensure_wiki_morning_delta_cron, _ensure_wiki_maintain_cron, reconcile_second_brain_cron_ids, repair_wiki_delta_job_security, _run_read_it_later_hygiene

[POS]
Second Brain preset: cron job lookup, blueprint provisioning, reconcile and repair.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from myrm_agent_harness.toolkits.cron.types import CronJobPatch, JobType

from app.core.cron.blueprints import fill_blueprint
from app.core.cron.blueprints.job_spec import create_blueprint_job, to_job_spec
from app.services.wiki.vault import resolve_agent_wiki_vault_path

from . import common
from .common import (
    _CRON_DELTA_JOB_NAME,
    _CRON_JOB_NAME,
    _CRON_MAINTAIN_JOB_NAME,
    logger,
)
from .job_repair import repair_wiki_delta_job


async def _find_preset_cron_job(*, job_name: str, stored_job_id: str | None) -> str | None:
    mgr = common.get_cron_manager()
    jobs = await mgr.list_jobs()
    for job in jobs:
        if job.name == job_name or job.name.startswith(f"{job_name} ("):
            return job.id
    if stored_job_id:
        existing = await mgr.get_job(stored_job_id)
        if existing is not None:
            return existing.id
    return None


async def _find_read_it_later_cron_job() -> str | None:
    state = await common._load_preset_state()
    stored_id = state.cron_job_id if state else None
    return await _find_preset_cron_job(job_name=_CRON_JOB_NAME, stored_job_id=stored_id)


async def _find_wiki_morning_delta_cron_job() -> str | None:
    state = await common._load_preset_state()
    stored_id = state.delta_cron_job_id if state else None
    return await _find_preset_cron_job(job_name=_CRON_DELTA_JOB_NAME, stored_job_id=stored_id)


async def _find_wiki_maintain_cron_job() -> str | None:
    state = await common._load_preset_state()
    stored_id = state.maintain_cron_job_id if state else None
    return await _find_preset_cron_job(job_name=_CRON_MAINTAIN_JOB_NAME, stored_job_id=stored_id)


async def _ensure_blueprint_cron(
    *,
    blueprint_id: str,
    job_name: str,
    slot_values: dict[str, str],
    agent_id: str,
    locale: str,
    find_existing_job_id: Callable[[], Awaitable[str | None]],
    allowed_roots: tuple[str, ...] = (),
) -> tuple[str | None, bool]:
    mgr = common.get_cron_manager()
    fill = fill_blueprint(blueprint_id, slot_values, locale=locale)
    if fill is None:
        raise common.SecondBrainPresetError(f"{blueprint_id} cron blueprint is unavailable")

    existing_id = await find_existing_job_id()
    if existing_id:
        job = await mgr.get_job(existing_id)
        if job is not None:
            needs_rebuild = fill.command is not None and (job.command != fill.command or job.job_type != JobType(fill.job_type))
            if needs_rebuild:
                await mgr.delete_job(existing_id)
                existing_id = None
            elif job.agent_id != agent_id:
                await mgr.update_job(
                    existing_id,
                    CronJobPatch(agent_id=agent_id, allowed_roots=allowed_roots or None),
                )
                return existing_id, False
            else:
                return existing_id, False

    job = await create_blueprint_job(
        mgr,
        to_job_spec(fill),
        name=job_name,
        agent_id=agent_id,
        allowed_roots=allowed_roots,
        default_timeout_seconds=300,
    )
    return job.id, True


async def _ensure_read_it_later_cron(*, agent_id: str, locale: str) -> tuple[str | None, bool]:
    return await _ensure_blueprint_cron(
        blueprint_id="read_it_later",
        job_name=_CRON_JOB_NAME,
        slot_values={"time": "06:00", "weekdays": "everyday"},
        agent_id=agent_id,
        locale=locale,
        find_existing_job_id=_find_read_it_later_cron_job,
    )


async def _ensure_wiki_morning_delta_cron(*, agent_id: str, locale: str) -> tuple[str | None, bool]:
    return await _ensure_blueprint_cron(
        blueprint_id="wiki_morning_delta",
        job_name=_CRON_DELTA_JOB_NAME,
        slot_values={"time": "07:00", "weekdays": "everyday"},
        agent_id=agent_id,
        locale=locale,
        find_existing_job_id=_find_wiki_morning_delta_cron_job,
        allowed_roots=(str(resolve_agent_wiki_vault_path(agent_id)),),
    )


async def _ensure_wiki_maintain_cron(*, agent_id: str, locale: str) -> tuple[str | None, bool]:
    return await _ensure_blueprint_cron(
        blueprint_id="wiki_maintain",
        job_name=_CRON_MAINTAIN_JOB_NAME,
        slot_values={"time": "03:00", "weekdays": "weekends", "mode": "full"},
        agent_id=agent_id,
        locale=locale,
        find_existing_job_id=_find_wiki_maintain_cron_job,
    )


async def reconcile_second_brain_cron_ids(id_remaps: dict[str, str]) -> None:
    """Update stored preset cron ids after read-it-later hygiene recreates jobs."""
    if not id_remaps:
        return
    state = await common._load_preset_state()
    if state is None:
        return
    cron_job_id = id_remaps.get(state.cron_job_id, state.cron_job_id) if state.cron_job_id else None
    delta_cron_job_id = id_remaps.get(state.delta_cron_job_id, state.delta_cron_job_id) if state.delta_cron_job_id else None
    maintain_cron_job_id = (
        id_remaps.get(state.maintain_cron_job_id, state.maintain_cron_job_id) if state.maintain_cron_job_id else None
    )
    if (
        cron_job_id == state.cron_job_id
        and delta_cron_job_id == state.delta_cron_job_id
        and maintain_cron_job_id == state.maintain_cron_job_id
    ):
        return
    await common._save_preset_state(
        state.model_copy(
            update={
                "cron_job_id": cron_job_id,
                "delta_cron_job_id": delta_cron_job_id,
                "maintain_cron_job_id": maintain_cron_job_id,
            }
        )
    )


async def repair_wiki_delta_job_security() -> bool:
    """Startup repair of a wiki-delta job created before its capability declaration was fixed."""
    job_id = await _find_wiki_morning_delta_cron_job()
    return job_id is not None and await repair_wiki_delta_job(job_id)


async def _run_read_it_later_hygiene() -> None:
    from app.services.wiki.source_sync.read_it_later_hygiene import (
        migrate_stale_read_it_later_jobs,
    )

    result = await migrate_stale_read_it_later_jobs()
    if result.migrated_count:
        logger.info("Read-it-later cron hygiene migrated %d job(s)", result.migrated_count)
    await reconcile_second_brain_cron_ids(result.id_remaps)
