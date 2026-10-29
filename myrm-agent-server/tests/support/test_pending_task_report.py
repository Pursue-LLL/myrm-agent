"""Unit tests for the pending-task report: it names the await a stuck task is parked on and stays quiet for a block that ends in time."""

from __future__ import annotations

import asyncio
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.pending_task_report import pending_task_report, report_pending_tasks_after

_REPORT_WITHIN_SECONDS = 10.0


@contextmanager
def _loop_with_a_task_parked_on_an_event() -> Iterator[None]:
    """A loop on its own thread, as the test client's portal runs one, with a task that never gets its event."""
    started = threading.Event()
    stop = threading.Event()

    async def _never_set_event_wait() -> None:
        await asyncio.Event().wait()

    async def _run() -> None:
        stuck = asyncio.create_task(_never_set_event_wait(), name="stuck-turn")
        started.set()
        while not stop.is_set():
            await asyncio.sleep(0.01)
        stuck.cancel()

    worker = threading.Thread(target=lambda: asyncio.run(_run()), daemon=True)
    worker.start()
    assert started.wait(5.0)
    try:
        yield
    finally:
        stop.set()
        worker.join(5.0)


def test_the_report_names_the_task_and_the_await_it_is_parked_on() -> None:
    with _loop_with_a_task_parked_on_an_event():
        report = pending_task_report()

    assert "stuck-turn" in report
    assert "_never_set_event_wait" in report


def test_a_block_that_outlives_the_deadline_writes_the_report(capfd: pytest.CaptureFixture[str]) -> None:
    """The report walks every live object, which takes longer the bigger the process is (0.7 s with 1.1 million objects), so the test waits for it."""
    written = ""
    with _loop_with_a_task_parked_on_an_event(), report_pending_tasks_after(0.05):
        give_up_at = time.monotonic() + _REPORT_WITHIN_SECONDS
        while "stuck-turn" not in written and time.monotonic() < give_up_at:
            time.sleep(0.05)
            written += capfd.readouterr().err

    assert "stuck-turn" in written


def test_a_block_that_ends_in_time_writes_nothing(capfd: pytest.CaptureFixture[str]) -> None:
    with report_pending_tasks_after(0.3):
        pass
    time.sleep(0.5)

    assert capfd.readouterr().err == ""
