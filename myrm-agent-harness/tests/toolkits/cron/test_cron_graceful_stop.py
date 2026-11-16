"""A graceful stop records the runs it cuts off before it cancels them, counts nothing, and still fits a short exit.

The records are written first because a host may force-kill a slow exit; the cancel then gets half a second to unwind
and no more, and the scheduler lock is released last. A store that cannot record keeps none of that from happening.
Every test drives the real scheduler and recovery over the in-memory store; only the runner, the lock and the injected
store faults are stand-ins.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.engine import scheduler as scheduler_module
from myrm_agent_harness.toolkits.cron.types import JobStatus
from tests.support.cron_inflight_stack import STOPPING, EventLock, InflightStack, YieldingStore, make_inflight_stack


@pytest.fixture
def stack() -> InflightStack:
    return make_inflight_stack()


@pytest.fixture(autouse=True)
def _no_timers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the test acts: the scheduler's own timers must never fire."""
    for name in ("_MIN_REFIRE_GAP_S", "_WATCHDOG_INTERVAL_S", "_STARTUP_TICK_DELAY_S"):
        monkeypatch.setattr(scheduler_module, name, 3600.0)


async def test_a_stop_records_the_run_before_it_cancels_it_and_counts_nothing() -> None:
    stack = make_inflight_stack(YieldingStore())
    job = await stack.add()
    await stack.launch(job)

    await stack.scheduler.stop()
    await stack.drain()

    assert stack.runner.records_when_cancelled == [1], "the record was durable before the cancel reached the run"
    assert await stack.interrupted() == [("shutdown", STOPPING)]
    stored = await stack.stored()
    assert (stored.consecutive_failures, stored.status) == (0, JobStatus.ACTIVE) and stored.next_run_at is not None
    assert await stack.markers() == [] and not stack.scheduler._in_flight


async def test_a_stop_waits_half_a_second_for_a_slow_unwinding_run_and_no_longer(stack: InflightStack) -> None:
    stack.runner.unwind_s = 30
    await stack.launch(await stack.add())

    started = time.monotonic()
    await stack.scheduler.stop()
    elapsed = time.monotonic() - started

    assert 0.45 <= elapsed < 2.0
    assert [task for task in stack.scheduler._bg_tasks if not task.done()], "the run is still unwinding"
    stack.runner.unwind_s = 0
    await stack.end_runs()


async def test_a_stop_releases_the_lock_after_the_records(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[str] = []
    stack = make_inflight_stack(lock=EventLock(events))
    save_run = stack.store.save_run

    async def logging_save_run(run: object) -> None:
        events.append("record written")
        await save_run(run)  # type: ignore[arg-type]

    monkeypatch.setattr(stack.store, "save_run", logging_save_run)
    await stack.scheduler.start()
    await stack.launch(await stack.add())

    await stack.scheduler.stop()

    assert events == ["record written", "lock released"]


async def test_a_store_that_cannot_record_does_not_keep_the_stop_from_cancelling_and_releasing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    events: list[str] = []
    stack = make_inflight_stack(lock=EventLock(events))
    monkeypatch.setattr(stack.store, "list_running", AsyncMock(side_effect=OSError("database is locked")))
    await stack.launch(await stack.add())

    with caplog.at_level(logging.WARNING):
        await stack.scheduler.stop()
    await stack.drain()

    assert stack.runner.records_when_cancelled == [0] and events == ["lock released"]
    assert "could not record the interrupted runs" in caplog.text


async def test_a_stop_with_no_run_in_flight_reads_no_markers(monkeypatch: pytest.MonkeyPatch) -> None:
    stack = make_inflight_stack()
    spy = AsyncMock(wraps=stack.store.list_running)
    monkeypatch.setattr(stack.store, "list_running", spy)

    await stack.scheduler.stop()

    spy.assert_not_called()


async def test_a_restart_after_a_stop_reports_nothing_twice(stack: InflightStack) -> None:
    await stack.launch(await stack.add())
    await stack.scheduler.stop()
    await stack.drain()

    stack.runner.gate.set()  # the slot the stop cut off is still due: the restart runs it again
    await stack.scheduler.start()
    await stack.drain()

    sources = sorted(str(source) for source, _ in await stack.interrupted())
    assert sources == ["cron", "shutdown"], "the stop's record stands and nothing was reported as a crash"
    assert (await stack.stored()).consecutive_failures == 0
    await stack.scheduler.stop()
