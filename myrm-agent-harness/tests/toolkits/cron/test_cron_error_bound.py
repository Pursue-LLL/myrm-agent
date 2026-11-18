"""The error text a failed run leaves behind is bounded, on the run record and on the job alike.

A shell job's stderr can be megabytes and the job travels with every list call, so only a bounded head and tail is
stored. What a run decides still reads the full error: a transient keyword in the part the cut dropped must retry.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine.run_closer import MAX_STORED_ERROR_CHARS
from myrm_agent_harness.toolkits.cron.types import JobResult, JobStatus, ScheduleKind
from tests.support.cron_executor_mocks import make_executor, make_job, make_schedule, store_holds

_CAUSE = "ValueError: the payload has no customer id"
_KEYWORD = "rate limit exceeded"  # a transient error: a one-shot job that fails with it is retried
_FILLER = "x" * (MAX_STORED_ERROR_CHARS * 5)


def _failure(error: str) -> AsyncMock:
    runner = AsyncMock()
    runner.run = AsyncMock(return_value=JobResult(success=False, error=error))
    return runner


def _with_cause_last(*parts: str) -> str:
    """Filler first and the cause on the last line, as a traceback ends."""
    return "\n".join([*parts, _CAUSE])


class TestRecurringJob:
    @pytest.mark.asyncio
    async def test_run_and_job_store_the_same_bounded_error(self) -> None:
        executor, store, _ = make_executor()
        job = make_job()
        store_holds(store, job)

        await executor.run_and_record(job, _failure(_with_cause_last(_FILLER)))

        run = store.save_run.call_args[0][0]
        assert run.error is not None
        assert len(run.error) <= MAX_STORED_ERROR_CHARS
        assert _CAUSE in run.error
        assert job.last_error == run.error

    @pytest.mark.asyncio
    async def test_an_error_within_the_bound_is_stored_as_it_is(self) -> None:
        executor, store, _ = make_executor()
        job = make_job()
        store_holds(store, job)

        await executor.run_and_record(job, _failure(_CAUSE))

        assert store.save_run.call_args[0][0].error == _CAUSE
        assert job.last_error == _CAUSE


class TestManualRun:
    @pytest.mark.asyncio
    async def test_the_trial_outcome_is_bounded_too(self) -> None:
        executor, store, _ = make_executor()
        job = make_job()
        store_holds(store, job)

        await executor.run_and_record(job, _failure(_with_cause_last(_FILLER)), trigger_source="manual")

        assert job.last_error is not None
        assert len(job.last_error) <= MAX_STORED_ERROR_CHARS
        assert _CAUSE in job.last_error


class TestOneShotJob:
    @pytest.mark.asyncio
    async def test_a_terminal_failure_stores_a_bounded_error(self) -> None:
        executor, store, _ = make_executor()
        job = make_job(schedule=make_schedule(ScheduleKind.ONCE))
        store_holds(store, job)

        await executor.run_and_record(job, _failure(_with_cause_last(_FILLER)))

        assert job.status == JobStatus.PAUSED
        assert job.last_error is not None
        assert len(job.last_error) <= MAX_STORED_ERROR_CHARS
        assert _CAUSE in job.last_error

    @pytest.mark.asyncio
    async def test_a_retried_failure_stores_a_bounded_error(self) -> None:
        executor, store, _ = make_executor()
        job = make_job(schedule=make_schedule(ScheduleKind.ONCE))
        store_holds(store, job)

        await executor.run_and_record(job, _failure(_with_cause_last(_KEYWORD, _FILLER)))

        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at is not None
        assert job.last_error is not None
        assert len(job.last_error) <= MAX_STORED_ERROR_CHARS

    @pytest.mark.asyncio
    async def test_a_transient_keyword_the_cut_dropped_still_retries(self) -> None:
        """The keyword sits mid-text, in the part the stored error no longer holds: the decision read the full error."""
        executor, store, _ = make_executor()
        job = make_job(schedule=make_schedule(ScheduleKind.ONCE))
        store_holds(store, job)

        await executor.run_and_record(job, _failure(_with_cause_last(_FILLER, _KEYWORD, _FILLER)))

        assert job.last_error is not None
        assert _KEYWORD not in job.last_error
        assert job.status == JobStatus.ACTIVE
        assert job.next_run_at is not None
