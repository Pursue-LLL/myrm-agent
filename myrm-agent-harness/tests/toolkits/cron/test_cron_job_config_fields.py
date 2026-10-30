"""A job's configuration reaches the stored job through create, update and duplicate; duplicate starts the run state fresh."""

from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime
from unittest.mock import MagicMock

from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.triggers import TriggerConfig, WebhookTrigger
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronJobPatch,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

_USER = "user-1"
_LONG_AGO = datetime(2020, 1, 1, tzinfo=UTC)

# Fields a duplicate must not inherit: the run history of the source job.
_RUN_STATE: dict[str, object] = {
    "fire_count": 7,
    "last_output_hash": "abc123",
    "job_scratchpad": {"seen": "3"},
    "last_run_at": _LONG_AGO,
    "last_status": RunStatus.ERROR,
    "last_error": "boom",
    "consecutive_failures": 3,
    "last_failure_alert_at": _LONG_AGO,
}
# Fields a duplicate gets new values for: its identity and its place in the schedule.
_IDENTITY = {"id", "name", "status", "next_run_at", "created_at", "updated_at"}


def _manager() -> tuple[CronManager, InMemoryCronStore]:
    store = InMemoryCronStore()
    return CronManager(store=store, scheduler=MagicMock()), store


async def _create(mgr: CronManager, **kwargs: object) -> CronJob:
    return await mgr.create_job(
        _USER,
        "Nightly",
        JobType.AGENT,
        Schedule(kind=ScheduleKind.CRON, expr="0 * * * *"),
        prompt="summarise",
        **kwargs,  # type: ignore[arg-type]
    )


async def _configured_source(mgr: CronManager, store: InMemoryCronStore) -> CronJob:
    """A stored job with non-default configuration and a non-trivial run history."""
    job = await _create(
        mgr,
        skip_if_active=True,
        deduplicate=True,
        tools_allowed=("web_search",),
        skill_ids=("skill-a",),
        timeout_seconds=120,
        max_retries=5,
        pre_condition_script="test -f /tmp/ready",
        acceptance_criteria=({"type": "shell", "command": "test -s out.txt"},),
    )
    job.continuity = True
    job.target_bot_agent_id = "bot-1"
    job.created_at = job.updated_at = _LONG_AGO
    for name, value in _RUN_STATE.items():
        setattr(job, name, value)
    return await store.save_job(job)


async def test_create_job_stores_skip_if_active() -> None:
    mgr, store = _manager()

    on = await _create(mgr, skip_if_active=True)
    off = await _create(mgr)

    assert (await store.get_job(on.id)).skip_if_active is True  # type: ignore[union-attr]
    assert (await store.get_job(off.id)).skip_if_active is False  # type: ignore[union-attr]


async def test_update_job_applies_skip_if_active_and_keeps_it_when_the_patch_is_silent() -> None:
    mgr, store = _manager()
    job = await _create(mgr)

    await mgr.update_job(job.id, _USER, CronJobPatch(skip_if_active=True))
    assert (await store.get_job(job.id)).skip_if_active is True  # type: ignore[union-attr]

    await mgr.update_job(job.id, _USER, CronJobPatch(name="Renamed"))
    assert (await store.get_job(job.id)).skip_if_active is True  # type: ignore[union-attr]

    await mgr.update_job(job.id, _USER, CronJobPatch(skip_if_active=False))
    assert (await store.get_job(job.id)).skip_if_active is False  # type: ignore[union-attr]


async def test_duplicate_job_carries_every_configuration_field() -> None:
    mgr, store = _manager()
    source = await _configured_source(mgr, store)

    copy = await mgr.duplicate_job(source.id, _USER)

    assert copy is not None
    assert copy.acceptance_criteria == source.acceptance_criteria != ()
    assert copy.skip_if_active is True
    assert copy.continuity is True
    assert copy.target_bot_agent_id == "bot-1"
    assert copy.deduplicate is True
    assert copy.pre_condition_script == "test -f /tmp/ready"
    assert copy.tools_allowed == ("web_search",)
    assert copy.skill_ids == ("skill-a",)
    assert (copy.timeout_seconds, copy.max_retries) == (120, 5)


async def test_duplicate_job_starts_paused_with_a_new_identity_and_no_run_history() -> None:
    mgr, store = _manager()
    source = await _configured_source(mgr, store)

    copy = await mgr.duplicate_job(source.id, _USER)

    assert copy is not None
    assert copy.id != source.id
    assert copy.name == "Nightly (Copy)"
    assert copy.status == JobStatus.PAUSED
    assert copy.next_run_at is None
    assert copy.created_at > _LONG_AGO
    assert (copy.fire_count, copy.consecutive_failures) == (0, 0)
    assert (copy.last_run_at, copy.last_status, copy.last_error, copy.last_failure_alert_at) == (None,) * 4
    assert copy.last_output_hash is None
    assert copy.job_scratchpad == {}


async def test_duplicate_job_differs_from_its_source_only_in_identity_and_run_state() -> None:
    mgr, store = _manager()
    source = await _configured_source(mgr, store)

    copy = await mgr.duplicate_job(source.id, _USER)

    assert copy is not None
    changed = {f.name for f in fields(CronJob) if getattr(copy, f.name) != getattr(source, f.name)}
    assert changed == _IDENTITY | set(_RUN_STATE)


async def test_duplicate_job_gives_every_webhook_its_own_path_and_secret() -> None:
    mgr, _ = _manager()
    source = await _create(mgr, triggers=TriggerConfig(webhooks=(WebhookTrigger(), WebhookTrigger())))

    copy = await mgr.duplicate_job(source.id, _USER)

    assert copy is not None and copy.triggers is not None and source.triggers is not None
    assert len(copy.triggers.webhooks) == 2
    for original, duplicate in zip(source.triggers.webhooks, copy.triggers.webhooks, strict=True):
        assert duplicate.path and duplicate.secret
        assert (duplicate.path, duplicate.secret) != (original.path, original.secret)


async def test_duplicating_twice_gives_distinct_names() -> None:
    mgr, _ = _manager()
    source = await _create(mgr)

    first = await mgr.duplicate_job(source.id, _USER)
    second = await mgr.duplicate_job(source.id, _USER)

    assert first is not None and second is not None
    assert len({source.name, first.name, second.name}) == 3


async def test_duplicate_job_of_a_missing_or_foreign_job_is_none() -> None:
    mgr, _ = _manager()
    source = await _create(mgr)

    assert await mgr.duplicate_job("missing", _USER) is None
    assert await mgr.duplicate_job(source.id, "someone-else") is None
