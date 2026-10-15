"""Wiki maintain runs one at a time per vault scope, in the background for REST and blocking for cron."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.wiki.maintenance.modes import MaintainMode
from myrm_agent_harness.toolkits.wiki.maintenance.progress import MaintainPhase, MaintainProgress

from app.services.wiki.maintain import (
    WikiMaintainRunResult,
    cancel_wiki_maintain,
    get_wiki_maintain_run,
    run_registry,
    run_wiki_maintain_job,
    runner,
    schedule_wiki_maintain,
)
from app.services.wiki.maintain.run_registry import MaintainRunState, start_wiki_maintain_run

_PIPELINE = "app.services.wiki.maintain.runner._run_maintain_pipeline"


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    run_registry._runs.clear()
    yield
    run_registry._runs.clear()


def _idle_archiver() -> MagicMock:
    archiver = MagicMock()
    archiver._queue.get_stats.return_value = {"processing": 0}
    return archiver


def _finished(mode: str = "full", links: int = 0) -> WikiMaintainRunResult:
    return WikiMaintainRunResult(mode=mode, issues_found=1, connections_discovered=links)  # type: ignore[arg-type]


def _gated_pipeline(gate: asyncio.Event, result: WikiMaintainRunResult) -> Callable[..., Awaitable[WikiMaintainRunResult]]:
    async def _run(**_kwargs: object) -> WikiMaintainRunResult:
        await gate.wait()
        return result

    return _run


# --- registry -------------------------------------------------------------------------------


def test_a_scope_cannot_start_a_second_run_while_one_is_running() -> None:
    first = start_wiki_maintain_run("agent-1", "full")

    assert first is not None
    assert start_wiki_maintain_run("agent-1", "structural") is None
    assert start_wiki_maintain_run("agent-2", "full") is not None
    assert start_wiki_maintain_run(None, "full") is not None
    assert get_wiki_maintain_run("agent-1") is first


def test_a_finished_run_frees_the_scope_and_keeps_its_outcome_until_the_next_run() -> None:
    run = start_wiki_maintain_run("agent-1", "full")
    assert run is not None
    result = _finished(links=3)

    run.finish(result)

    assert run.state is MaintainRunState.SUCCEEDED
    assert get_wiki_maintain_run("agent-1") is run
    assert run.result is result
    assert start_wiki_maintain_run("agent-1", "full") is not run


def test_cancelling_asks_the_run_in_flight_to_stop_and_can_be_repeated() -> None:
    run = start_wiki_maintain_run("agent-1", "full")
    assert run is not None

    assert cancel_wiki_maintain("agent-1") is run
    assert cancel_wiki_maintain("agent-1") is run

    assert run.stop.is_set()
    assert run.state is MaintainRunState.RUNNING


def test_cancelling_reaches_only_the_run_of_its_own_scope() -> None:
    mine = start_wiki_maintain_run("agent-1", "full")
    other = start_wiki_maintain_run("agent-2", "full")
    assert mine is not None and other is not None

    cancel_wiki_maintain("agent-1")

    assert mine.stop.is_set()
    assert not other.stop.is_set()


def test_cancelling_without_a_run_in_flight_leaves_no_trace() -> None:
    assert cancel_wiki_maintain("nobody") is None

    run = start_wiki_maintain_run("agent-1", "full")
    assert run is not None
    run.finish(_finished())

    assert cancel_wiki_maintain("agent-1") is run
    assert not run.stop.is_set()
    assert run.state is MaintainRunState.SUCCEEDED


def test_a_run_that_stopped_early_is_cancelled_and_still_frees_the_scope() -> None:
    run = start_wiki_maintain_run("agent-1", "full")
    assert run is not None
    partial = WikiMaintainRunResult(mode="full", issues_fixed=1, connections_discovered=2, cancelled=True)

    run.finish(partial)

    assert run.state is MaintainRunState.CANCELLED
    assert run.result is partial
    assert start_wiki_maintain_run("agent-1", "full") is not run


def test_progress_updates_the_run() -> None:
    run = start_wiki_maintain_run(None, "full")
    assert run is not None

    run.on_progress(MaintainProgress(MaintainPhase.LINK_DISCOVERY, 7, 20))

    assert (run.phase, run.done, run.total) == (MaintainPhase.LINK_DISCOVERY, 7, 20)


# --- blocking run (cron) --------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_second_blocking_run_is_skipped_silently_and_the_first_still_completes() -> None:
    gate = asyncio.Event()
    expected = _finished(links=2)
    with patch(_PIPELINE, new=_gated_pipeline(gate, expected)):
        first = asyncio.create_task(run_wiki_maintain_job(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL))
        await asyncio.sleep(0)

        # Without the single flight this call would wait on the gate too: fail the test instead of hanging it.
        second = await asyncio.wait_for(
            run_wiki_maintain_job(llm=MagicMock(), agent_id="a", mode=MaintainMode.STRUCTURAL), timeout=5
        )
        gate.set()
        completed = await first

    assert second.skipped is True
    assert second.skipped_reason == "maintain_in_progress"
    assert second.summary_text == "[SILENT]"
    assert completed is expected
    assert start_wiki_maintain_run("a", "full") is not None


@pytest.mark.asyncio
async def test_a_blocking_run_frees_the_scope_when_it_fails() -> None:
    with patch(_PIPELINE, new=AsyncMock(side_effect=RuntimeError("provider exploded"))):
        with pytest.raises(RuntimeError):
            await run_wiki_maintain_job(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)

    run = get_wiki_maintain_run("a")
    assert run is not None
    assert (run.state, run.error_code) == (MaintainRunState.FAILED, "maintain_failed")
    assert start_wiki_maintain_run("a", "full") is not None


@pytest.mark.asyncio
async def test_a_read_only_listing_does_not_wait_for_the_running_maintenance() -> None:
    listing = WikiMaintainRunResult(mode="list_only", summary_text="report")
    pipeline = AsyncMock(return_value=listing)
    running = start_wiki_maintain_run("a", "full")
    assert running is not None

    with patch(_PIPELINE, new=pipeline):
        result = await run_wiki_maintain_job(llm=None, agent_id="a", mode="list_only")

    assert result is listing
    assert get_wiki_maintain_run("a") is running
    assert running.state is MaintainRunState.RUNNING


@pytest.mark.asyncio
async def test_the_pipeline_receives_the_progress_observer_of_its_run() -> None:
    seen: list[object] = []

    async def _pipeline(**kwargs: object) -> WikiMaintainRunResult:
        seen.append(kwargs["on_progress"])
        return _finished()

    with patch(_PIPELINE, new=_pipeline):
        await run_wiki_maintain_job(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)

    assert seen == [get_wiki_maintain_run("a").on_progress]  # type: ignore[union-attr]


# --- background run (REST) ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_scheduling_starts_a_background_run_and_records_its_outcome() -> None:
    gate = asyncio.Event()
    expected = _finished(links=4)

    async def _pipeline(*, on_progress: Callable[[MaintainProgress], None], **_kwargs: object) -> WikiMaintainRunResult:
        on_progress(MaintainProgress(MaintainPhase.LINK_DISCOVERY, 3, 20))
        await gate.wait()
        return expected

    with (
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=_idle_archiver()),
        patch(_PIPELINE, new=_pipeline),
    ):
        scheduled = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        run = scheduled.run
        assert run is not None
        await asyncio.sleep(0)
        assert (run.state, run.phase, run.done, run.total) == (MaintainRunState.RUNNING, MaintainPhase.LINK_DISCOVERY, 3, 20)

        gate.set()
        assert run.task is not None
        await run.task

    assert run.state is MaintainRunState.SUCCEEDED
    assert run.result is expected
    assert run.error_code is None


@pytest.mark.asyncio
async def test_cancelling_a_background_run_stops_its_pipeline_and_records_it_as_cancelled() -> None:
    partial = WikiMaintainRunResult(mode="full", connections_discovered=2, cancelled=True)

    async def _pipeline(*, stop: asyncio.Event, **_kwargs: object) -> WikiMaintainRunResult:
        await stop.wait()
        return partial

    with (
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=_idle_archiver()),
        patch(_PIPELINE, new=_pipeline),
    ):
        scheduled = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        run = scheduled.run
        assert run is not None and run.task is not None
        await asyncio.sleep(0)
        assert run.state is MaintainRunState.RUNNING

        cancel_wiki_maintain("a")
        await asyncio.wait_for(run.task, timeout=5)

    assert run.state is MaintainRunState.CANCELLED
    assert run.result is partial
    assert run.error_code is None
    assert start_wiki_maintain_run("a", "full") is not None


@pytest.mark.asyncio
async def test_scheduling_while_running_attaches_to_the_run_in_flight() -> None:
    gate = asyncio.Event()
    pipeline = MagicMock(side_effect=_gated_pipeline(gate, _finished()))

    with (
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=_idle_archiver()),
        patch(_PIPELINE, new=pipeline),
    ):
        first = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        second = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        gate.set()
        assert first.run is not None and first.run.task is not None
        await first.run.task

    assert second.run is first.run
    assert second.skipped_reason is None
    assert pipeline.call_count == 1


@pytest.mark.asyncio
async def test_scheduling_is_refused_while_a_compile_runs() -> None:
    busy = MagicMock()
    busy._queue.get_stats.return_value = {"processing": 2}
    pipeline = AsyncMock()

    with patch("app.services.wiki.vault.get_wiki_archiver", return_value=busy), patch(_PIPELINE, new=pipeline):
        scheduled = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)

    assert scheduled.run is None
    assert scheduled.skipped_reason == "compile_in_progress"
    assert get_wiki_maintain_run("a") is None
    pipeline.assert_not_called()


@pytest.mark.asyncio
async def test_a_background_failure_keeps_only_an_error_code() -> None:
    with (
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=_idle_archiver()),
        patch(_PIPELINE, new=AsyncMock(side_effect=RuntimeError("secret provider detail"))),
    ):
        scheduled = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        assert scheduled.run is not None and scheduled.run.task is not None
        await scheduled.run.task

    run = scheduled.run
    assert run.state is MaintainRunState.FAILED
    assert run.error_code == "maintain_failed"
    assert run.result is None
    assert "secret" not in repr(run)
    assert start_wiki_maintain_run("a", "full") is not None


@pytest.mark.asyncio
async def test_a_compile_that_started_after_scheduling_is_reported_as_compile_busy() -> None:
    skipped = WikiMaintainRunResult(skipped=True, skipped_reason="compile_in_progress", mode="full", summary_text="[SILENT]")
    with (
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=_idle_archiver()),
        patch(_PIPELINE, new=AsyncMock(return_value=skipped)),
    ):
        scheduled = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        assert scheduled.run is not None and scheduled.run.task is not None
        await scheduled.run.task

    assert (scheduled.run.state, scheduled.run.error_code) == (MaintainRunState.FAILED, "compile_in_progress")


@pytest.mark.asyncio
async def test_a_run_over_the_time_cap_is_stopped_and_frees_the_scope(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(runner, "_RUN_TIMEOUT_SECONDS", 0.05)

    async def _never_finishes(**_kwargs: object) -> WikiMaintainRunResult:
        await asyncio.sleep(3600)
        return _finished()

    with (
        patch("app.services.wiki.vault.get_wiki_archiver", return_value=_idle_archiver()),
        patch(_PIPELINE, new=_never_finishes),
    ):
        scheduled = schedule_wiki_maintain(llm=MagicMock(), agent_id="a", mode=MaintainMode.FULL)
        assert scheduled.run is not None and scheduled.run.task is not None
        # Without the cap the pipeline above sleeps for an hour: fail the test instead of hanging it.
        await asyncio.wait_for(scheduled.run.task, timeout=5)

    assert (scheduled.run.state, scheduled.run.error_code) == (MaintainRunState.FAILED, "maintain_timeout")
    assert start_wiki_maintain_run("a", "full") is not None
