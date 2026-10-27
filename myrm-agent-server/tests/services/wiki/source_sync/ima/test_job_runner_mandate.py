"""A running ima slice ends when the sync is withdrawn: its job paused or removed, or its selection changed."""

from __future__ import annotations

import asyncio
import logging

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.services.wiki.source_sync.ima import job_runner
from app.services.wiki.source_sync.ima.context import SyncContext
from app.services.wiki.source_sync.ima.state import ImaKbSelection, ImaSyncConfig, save_ima_config

from .job_runner_support import LLM, POLL_S, Harness, configure

# A withdrawal must reach the slice within this long: about a hundred polls, so a slow machine does not flake it.
_PATIENCE_S = 1.0


async def _start_slices(
    harness: Harness,
    ima_db: async_sessionmaker[AsyncSession],
    *agents: str | None,
    libraries: tuple[ImaKbSelection, ...] = (),
) -> list[asyncio.Task[job_runner.ImaJobOutcome]]:
    """Start one slice per agent and wait until each has begun; they run until ``harness.gate`` is set."""
    harness.gate = asyncio.Event()
    for agent in agents:
        await configure(ima_db, libraries=libraries, agent_id=agent)
    begun = len(harness.contexts)
    runs = [asyncio.create_task(job_runner.run_ima_sync_job(llm=LLM, agent_id=agent)) for agent in agents]
    while len(harness.contexts) - begun < len(agents):
        await asyncio.sleep(0)
    return runs


async def _is_told_to_end(ctx: SyncContext) -> bool:
    try:
        await asyncio.wait_for(ctx.stop.wait(), timeout=_PATIENCE_S)
    except TimeoutError:
        return False
    return True


async def _stays_running(ctx: SyncContext) -> bool:
    """Let the watcher ask many times, then report whether the slice may still go on."""
    await asyncio.sleep(20 * POLL_S)
    return ctx.time_left() > 0


def _watchers() -> list[asyncio.Task[object]]:
    return [task for task in asyncio.all_tasks() if task.get_name() == "ima-sync-mandate"]


async def test_a_slice_ends_when_its_job_is_paused_or_removed_while_it_runs(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts
    assert ctx.time_left() > 0

    harness.pause(None)

    assert await _is_told_to_end(ctx)
    assert ctx.time_left() <= 0
    harness.release()
    await run


async def test_a_slice_ends_when_the_selection_changes_while_it_runs(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    async with ima_db() as db:
        await save_ima_config(
            db, ImaSyncConfig(knowledge_bases=[ImaKbSelection(id="kb1", name="One")], include_notes=True), agent_id=None
        )

    assert await _is_told_to_end(ctx)
    harness.release()
    await run


async def test_saving_the_same_selection_again_leaves_the_slice_alone(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    """The selection is which ids are imported: a renamed library or a save that changes nothing is no reason to restart."""
    (run,) = await _start_slices(harness, ima_db, None, libraries=(ImaKbSelection(id="kb1", name="One"),))
    (ctx,) = harness.contexts
    async with ima_db() as db:
        await save_ima_config(
            db, ImaSyncConfig(knowledge_bases=[ImaKbSelection(id="kb1", name="One, renamed")], include_notes=True), agent_id=None
        )

    assert await _stays_running(ctx)
    harness.release()
    await run


async def test_a_slice_asks_about_the_selection_of_its_own_agent(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    """Only the other agent has a selection; reading the default agent's instead would look like a change."""
    (run,) = await _start_slices(harness, ima_db, "other", libraries=(ImaKbSelection(id="kb1", name="One"),))
    (ctx,) = harness.contexts

    assert await _stays_running(ctx)
    harness.release()
    await run


async def test_a_slice_nobody_withdrew_runs_on(harness: Harness, ima_db: async_sessionmaker[AsyncSession]) -> None:
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    assert await _stays_running(ctx)
    harness.release()
    await run


async def test_a_withdrawal_reaches_only_the_slice_of_that_agent(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    runs = await _start_slices(harness, ima_db, None, "other")
    by_agent = {ctx.agent_id: ctx for ctx in harness.contexts}

    harness.pause("other")

    assert await _is_told_to_end(by_agent["other"])
    assert await _stays_running(by_agent[None])
    harness.release()
    await asyncio.gather(*runs)


async def test_a_pause_that_lands_right_after_the_job_was_read_is_still_noticed(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    """Nothing is registered anywhere, so no ordering against the slice's start can lose a pause: the job is asked as it is now."""
    harness.pause_after_admission = True
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    assert await _is_told_to_end(ctx)
    harness.release()
    await run


async def test_a_failed_check_does_not_end_the_slice_and_is_asked_again(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession], caplog: pytest.LogCaptureFixture
) -> None:
    harness.mandate_read_error = RuntimeError("database is locked")
    (run,) = await _start_slices(harness, ima_db, None)
    (ctx,) = harness.contexts

    assert await _stays_running(ctx)
    # However often it was asked, the failure is reported once.
    complaints = [record for record in caplog.records if "could not check" in record.getMessage()]
    assert [record.levelno for record in complaints] == [logging.WARNING]

    harness.mandate_read_error = None
    harness.pause(None)
    assert await _is_told_to_end(ctx)
    harness.release()
    await run


async def test_the_watcher_ends_with_the_slice_however_it_ends(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db)
    await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert _watchers() == []

    harness.slice_error = RuntimeError("transport died")
    with pytest.raises(RuntimeError, match="transport died"):
        await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)
    assert _watchers() == []

    harness.slice_error = None
    (run,) = await _start_slices(harness, ima_db, None)
    assert len(_watchers()) == 1
    run.cancel()
    with pytest.raises(asyncio.CancelledError):
        await run
    assert _watchers() == []


async def test_a_job_paused_or_removed_after_it_fired_starts_no_slice(
    harness: Harness, ima_db: async_sessionmaker[AsyncSession]
) -> None:
    await configure(ima_db)
    harness.pause(None)

    outcome = await job_runner.run_ima_sync_job(llm=LLM, agent_id=None)

    assert outcome.skipped and outcome.retry_at is None
    assert harness.contexts == [] and _watchers() == []
