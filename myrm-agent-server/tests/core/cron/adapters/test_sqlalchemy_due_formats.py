"""``list_jobs(due_before)`` and ``advance_next_run`` judge a stored next run time the same way, whatever its text format.

SQLite keeps ``next_run_at`` as text and compares it as text. A row reaches it in the ORM's own form
(``YYYY-MM-DD HH:MM:SS.ffffff``), without microseconds, or in an ISO form with a ``T`` separator. The store must book
exactly the jobs it lists as due: a job the dispatcher sees as due is booked once, a job it does not see is left alone.
A ``T`` row dated today compares later than every space-separated bound of today, so it is not due until the date rolls.

[INPUT]
- app.core.cron.adapters.sqlalchemy_store::SqlAlchemyCronStore (POS: the due filter of list_jobs and advance_next_run)
- tests.support.policy_sqlite::policy_database (POS: file SQLite running the production transaction policy)

[OUTPUT]
- for each stored text format: whether the row is listed as due, and that booking agrees with the listing

[POS]
Pins the one due comparison the SQL store makes for reading and for booking, so the two cannot drift apart.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind
from sqlalchemy import text

from app.core.cron.adapters.sqlalchemy_store import SqlAlchemyCronStore
from tests.support.policy_sqlite import PolicyDb, policy_database

_HOUR = timedelta(hours=1)
_ORM_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_NO_MICROSECONDS = "%Y-%m-%d %H:%M:%S"
_ISO_T = "%Y-%m-%dT%H:%M:%S.%f"


def _start_of_today(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


# label -> (stored text for the given instant, whether the row is due)
_CASES: dict[str, tuple[Callable[[datetime], str], bool]] = {
    "orm-format": (lambda now: (now - _HOUR).strftime(_ORM_FORMAT), True),
    "no-microseconds": (lambda now: (now - _HOUR).strftime(_NO_MICROSECONDS), True),
    "iso-t-earlier-today": (lambda now: _start_of_today(now).strftime(_ISO_T), False),
    "iso-t-yesterday": (lambda now: (now - timedelta(days=1)).strftime(_ISO_T), True),
    "future": (lambda now: (now + _HOUR).strftime(_ORM_FORMAT), False),
}


@pytest_asyncio.fixture
async def policy_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[PolicyDb]:
    async with policy_database(tmp_path / "cron.db", monkeypatch) as db:
        yield db


async def _store_with_stored_text(db: PolicyDb, stored: str) -> SqlAlchemyCronStore:
    store = SqlAlchemyCronStore()
    await store.save_job(
        CronJob(
            id="job",
            name="job",
            job_type=JobType.ROUTER,
            schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000, stagger_ms=0),
            command="__probe__",
        )
    )
    async with db.factory() as session:
        await session.execute(text("UPDATE cron_jobs SET next_run_at = :stored WHERE id = 'job'"), {"stored": stored})
        await session.commit()
    return store


@pytest.mark.parametrize("label", _CASES)
async def test_listing_and_booking_agree_on_a_stored_text_format(policy_db: PolicyDb, label: str) -> None:
    make_text, due = _CASES[label]
    now = datetime.now(UTC)
    store = await _store_with_stored_text(policy_db, make_text(now))
    booked = now + 6 * _HOUR

    listed = {job.id for job in await store.list_jobs(due_before=datetime.now(UTC))}

    assert ("job" in listed) is due
    assert await store.advance_next_run("job", next_run_at=booked) is due
    if due:
        assert await store.advance_next_run("job", next_run_at=booked + _HOUR) is False
