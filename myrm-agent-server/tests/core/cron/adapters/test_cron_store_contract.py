"""The in-memory cron store answers like the SQLAlchemy store.

Scheduler and executor behaviour is exercised against ``InMemoryCronStore`` in many test files while production runs on
``SqlAlchemyCronStore``. Every case here runs against both, so the double cannot drift from the store it stands in for.
Two behaviours are deliberately outside the contract: ``CronJob.user_id`` (the SQL store does not persist it, so jobs
reload with the default owner) and the order of jobs (the SQL store orders by the database's insert time, not by
``CronJob.created_at``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.infra.incremental.types import MonitorState
from myrm_agent_harness.toolkits.cron.protocols import CronStore
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    JobStatus,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from tests.support.policy_sqlite import policy_database

_EPOCH = datetime(2030, 1, 1, tzinfo=UTC)

# Names that tell a literal substring match from a SQL LIKE pattern (`%`, `_`) and from its escape characters.
_NAMES = ("Daily Report", "weekly report", "Backup", "50% off", "a_b", "axb", "c/d", "e\\f")


@pytest_asyncio.fixture(params=["memory", "sqlalchemy"])
async def store(request: pytest.FixtureRequest, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[CronStore]:
    if request.param == "memory":
        yield InMemoryCronStore()
        return
    async with policy_database(tmp_path / "cron.db", monkeypatch):
        yield SqlAlchemyCronStore()


def _at(minutes: int) -> datetime:
    return _EPOCH + timedelta(minutes=minutes)


def _utc(moment: datetime | None) -> datetime | None:
    """The SQL store hands timestamps back as naive UTC; both forms name the same instant."""
    return moment.replace(tzinfo=UTC) if moment is not None and moment.tzinfo is None else moment


def _job(
    job_id: str,
    *,
    name: str | None = None,
    chat_id: str | None = None,
    project_id: str | None = None,
    status: JobStatus = JobStatus.ACTIVE,
    next_run_at: datetime | None = None,
) -> CronJob:
    return CronJob(
        id=job_id,
        name=name or job_id,
        job_type=JobType.ROUTER,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0),
        command="__probe__",
        chat_id=chat_id,
        project_id=project_id,
        status=status,
        next_run_at=next_run_at,
    )


def _run(
    run_id: str,
    job_id: str,
    *,
    minute: int,
    status: RunStatus = RunStatus.OK,
    integrity_hash: str = "",
) -> CronRunRecord:
    return CronRunRecord(
        id=run_id,
        job_id=job_id,
        started_at=_at(minute),
        finished_at=_at(minute) + timedelta(seconds=30),
        duration_ms=30_000,
        status=status,
        integrity_hash=integrity_hash,
    )


def _monitor(job_id: str, *, seen: list[str], failures: int = 0) -> MonitorState:
    return MonitorState(job_id=job_id, monitor_type="set", data={"seen": seen}, updated_at=_at(0), failure_count=failures)


def _ids(jobs: list[CronJob]) -> set[str]:
    return {job.id for job in jobs}


async def _save(store: CronStore, *jobs: CronJob) -> None:
    for job in jobs:
        await store.save_job(job)


@pytest.mark.parametrize(
    ("needle", "expected"),
    [
        ("REPORT", {"Daily Report", "weekly report"}),
        ("ackup", {"Backup"}),
        ("nothing like it", set()),
        ("", set(_NAMES)),
        ("%", {"50% off"}),
        ("_", {"a_b"}),
        ("a_b", {"a_b"}),
        ("/", {"c/d"}),
        ("\\", {"e\\f"}),
    ],
)
async def test_name_filter_is_a_literal_case_insensitive_substring(store: CronStore, needle: str, expected: set[str]) -> None:
    await _save(store, *(_job(f"job-{i}", name=name) for i, name in enumerate(_NAMES)))

    assert {job.name for job in await store.list_jobs(name_filter=needle)} == expected
    assert await store.count_jobs(name_filter=needle) == len(expected)


async def test_chat_and_project_filters_narrow_the_listing_and_the_count(store: CronStore) -> None:
    await _save(
        store,
        _job("a", chat_id="chat-1", project_id="proj-1"),
        _job("b", chat_id="chat-1", project_id="proj-2"),
        _job("c", chat_id="chat-2", project_id="proj-1"),
        _job("d"),
    )

    assert _ids(await store.list_jobs(chat_id="chat-1")) == {"a", "b"}
    assert _ids(await store.list_jobs(project_id="proj-1")) == {"a", "c"}
    assert _ids(await store.list_jobs(chat_id="chat-1", project_id="proj-1")) == {"a"}
    assert await store.count_jobs(chat_id="chat-1") == 2
    assert await store.count_jobs(project_id="proj-1") == 2
    assert await store.count_jobs(chat_id="chat-1", project_id="proj-1") == 1
    assert await store.count_jobs() == 4


async def test_limit_and_offset_bound_the_page(store: CronStore) -> None:
    await _save(store, *(_job(f"job-{i}") for i in range(5)))

    assert len(await store.list_jobs()) == 5
    assert len(await store.list_jobs(limit=2)) == 2
    assert len(await store.list_jobs(limit=2, offset=4)) == 1
    assert len(await store.list_jobs(offset=3)) == 2
    assert await store.list_jobs(offset=5) == []


async def test_due_before_lists_active_scheduled_jobs_up_to_and_including_the_cutoff(store: CronStore) -> None:
    await _save(
        store,
        _job("early", next_run_at=_at(5)),
        _job("late", next_run_at=_at(50)),
        _job("paused", status=JobStatus.PAUSED, next_run_at=_at(5)),
        _job("done", status=JobStatus.COMPLETED, next_run_at=_at(1)),
        _job("claimed"),
    )

    assert _ids(await store.list_jobs(due_before=_at(4))) == set()
    assert _ids(await store.list_jobs(due_before=_at(5))) == {"early"}
    assert _ids(await store.list_jobs(due_before=_at(60))) == {"early", "late"}


async def test_earliest_next_run_ignores_inactive_and_unscheduled_jobs(store: CronStore) -> None:
    assert await store.earliest_next_run() is None

    await _save(
        store,
        _job("later", next_run_at=_at(30)),
        _job("sooner", next_run_at=_at(10)),
        _job("paused", status=JobStatus.PAUSED, next_run_at=_at(1)),
        _job("claimed"),
    )

    assert _utc(await store.earliest_next_run()) == _at(10)


async def test_claim_due_clears_the_next_run_and_reports_the_job_as_orphaned(store: CronStore) -> None:
    await _save(
        store,
        _job("a", next_run_at=_at(5)),
        _job("b", next_run_at=_at(6)),
        _job("idle", status=JobStatus.PAUSED),
    )

    await store.claim_due(["a"])

    claimed, untouched = await store.get_job("a"), await store.get_job("b")
    assert claimed is not None
    assert claimed.next_run_at is None
    assert untouched is not None
    assert _utc(untouched.next_run_at) == _at(6)
    assert _ids(await store.list_orphaned_active()) == {"a"}


async def test_save_job_upserts_by_id_and_delete_job_reports_whether_a_row_went(store: CronStore) -> None:
    job = _job("one", name="v1")
    await store.save_job(job)
    await store.save_job(replace(job, name="v2"))

    stored = await store.get_job("one")
    assert stored is not None
    assert stored.name == "v2"
    assert await store.count_jobs() == 1
    assert await store.get_job("missing") is None
    assert await store.delete_job("one") is True
    assert await store.delete_job("one") is False
    assert await store.get_job("one") is None


async def test_runs_list_newest_first_with_filters_pagination_and_counts(store: CronStore) -> None:
    await _save(store, _job("job-a"), _job("job-b"))
    for run in (
        _run("r0", "job-a", minute=0),
        _run("r1", "job-a", minute=10, status=RunStatus.ERROR),
        _run("r2", "job-a", minute=20),
        _run("r3", "job-b", minute=30, status=RunStatus.ERROR),
    ):
        await store.save_run(run)

    assert [r.id for r in await store.list_runs("job-a")] == ["r2", "r1", "r0"]
    assert [r.id for r in await store.list_runs()] == ["r3", "r2", "r1", "r0"]
    assert [r.id for r in await store.list_runs("job-a", limit=1, offset=1)] == ["r1"]
    assert [r.id for r in await store.list_runs(status="error")] == ["r3", "r1"]
    assert await store.count_runs("job-a") == 3
    assert await store.count_runs(status="error") == 2
    assert await store.count_runs("job-a", status="error") == 1


async def test_purge_old_runs_removes_only_runs_finished_before_the_cutoff(store: CronStore) -> None:
    await _save(store, _job("job"))
    for run in (_run("old", "job", minute=0), _run("edge", "job", minute=10), _run("new", "job", minute=20)):
        await store.save_run(run)

    assert await store.purge_old_runs(_at(10) + timedelta(seconds=30)) == 1
    assert {r.id for r in await store.list_runs("job")} == {"edge", "new"}


async def test_latest_integrity_hash_comes_from_the_newest_hashed_run(store: CronStore) -> None:
    await _save(store, _job("job"))
    assert await store.get_latest_integrity_hash("job") is None

    await store.save_run(_run("r0", "job", minute=0, integrity_hash="h0"))
    await store.save_run(_run("r1", "job", minute=10, integrity_hash="h1"))
    await store.save_run(_run("r2", "job", minute=20))

    assert await store.get_latest_integrity_hash("job") == "h1"


async def test_delete_job_cascade_removes_the_runs_and_monitor_state_of_that_job_only(store: CronStore) -> None:
    await _save(store, _job("job"), _job("other"))
    await store.save_run(_run("r0", "job", minute=0))
    await store.save_run(_run("r1", "other", minute=1))
    await store.save_monitor_state(_monitor("job", seen=["u1"]))
    await store.save_monitor_state(_monitor("other", seen=["u2"]))

    assert await store.delete_job_cascade("job") is True

    assert await store.get_job("job") is None
    assert await store.count_runs("job") == 0
    assert await store.get_monitor_state("job") is None
    assert await store.count_runs("other") == 1
    assert await store.get_monitor_state("other") is not None
    assert await store.delete_job_cascade("job") is False


async def test_monitor_state_upserts_per_job_and_batch_reads_only_what_exists(store: CronStore) -> None:
    await _save(store, _job("job"))
    await store.save_monitor_state(_monitor("job", seen=["u1"]))
    await store.save_monitor_state(_monitor("job", seen=["u1", "u2"], failures=2))

    state = await store.get_monitor_state("job")
    assert state is not None
    assert (state.monitor_type, state.data, state.failure_count) == ("set", {"seen": ["u1", "u2"]}, 2)
    assert set(await store.batch_get_monitor_states(["job", "missing"])) == {"job"}
    assert await store.batch_get_monitor_states([]) == {}
    assert await store.get_monitor_state("missing") is None
    assert await store.delete_monitor_state("job") is True
    assert await store.delete_monitor_state("job") is False
