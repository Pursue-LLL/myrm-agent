"""The memory reindex runs one at a time in the background and keeps the state the Settings page polls."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest
from myrm_agent_harness.toolkits.memory._manager.reindex import ProgressCallback, ReindexResult

from app.services.memory import reindex_run
from app.services.memory.reindex_run import (
    ReindexBusyError,
    ReindexOutcome,
    ReindexRun,
    ReindexRunState,
    get_memory_reindex_run,
    schedule_memory_reindex,
)


@pytest.fixture(autouse=True)
def _clean_registry() -> Iterator[None]:
    reindex_run._latest_run = None
    yield
    reindex_run._latest_run = None


def _manager(reindex: Callable[..., object], embedding_model: str = "model-a") -> MagicMock:
    manager = MagicMock()
    manager.config.embedding_model = embedding_model
    manager.reindex_from_orphans = AsyncMock(side_effect=reindex)
    return manager


def _gated(gate: asyncio.Event, result: ReindexResult) -> Callable[..., object]:
    async def reindex(*, progress_cb: ProgressCallback | None = None) -> ReindexResult:
        if progress_cb is not None:
            progress_cb(40, 100, "migrating")
        await gate.wait()
        return result

    return reindex


def _open_gate() -> asyncio.Event:
    gate = asyncio.Event()
    gate.set()
    return gate


async def _finished(run: ReindexRun) -> None:
    assert run.task is not None
    await run.task


async def test_a_second_request_joins_the_run_in_flight_instead_of_paying_twice() -> None:
    gate = asyncio.Event()
    manager = _manager(_gated(gate, ReindexResult(migrated=3, skipped=0, failed=0)))

    first = schedule_memory_reindex(manager)
    second = schedule_memory_reindex(manager)
    await asyncio.sleep(0)
    gate.set()
    await _finished(first)

    assert second is first
    assert manager.reindex_from_orphans.await_count == 1


async def test_a_request_for_another_model_cannot_join_a_run_into_the_previous_one() -> None:
    gate = asyncio.Event()
    first = schedule_memory_reindex(_manager(_gated(gate, ReindexResult(migrated=3, skipped=0, failed=0)), "model-a"))
    other = _manager(_gated(_open_gate(), ReindexResult(migrated=0, skipped=0, failed=0)), "model-b")

    with pytest.raises(ReindexBusyError, match="model-a"):
        schedule_memory_reindex(other)

    other.reindex_from_orphans.assert_not_called()
    assert get_memory_reindex_run() is first
    gate.set()
    await _finished(first)


async def test_once_the_run_ended_the_other_model_gets_its_own_run() -> None:
    first = schedule_memory_reindex(_manager(_gated(_open_gate(), ReindexResult(1, 0, 0)), "model-a"))
    await _finished(first)

    second = schedule_memory_reindex(_manager(_gated(_open_gate(), ReindexResult(2, 0, 0)), "model-b"))
    await _finished(second)

    assert (first.embedding_model, second.embedding_model) == ("model-a", "model-b")
    assert second.result == ReindexOutcome(migrated=2, skipped=0, failed=0)


async def test_progress_is_visible_while_running_and_the_outcome_after() -> None:
    gate = asyncio.Event()
    result = ReindexResult(migrated=8, skipped=1, failed=1)
    run = schedule_memory_reindex(_manager(_gated(gate, result)))
    await asyncio.sleep(0)

    assert (run.state, run.done, run.total, run.result) == (ReindexRunState.RUNNING, 40, 100, None)

    gate.set()
    await _finished(run)

    assert run.state is ReindexRunState.SUCCEEDED
    assert run.result == ReindexOutcome(migrated=8, skipped=1, failed=1)
    assert get_memory_reindex_run() is run


async def test_a_finished_run_frees_the_slot_for_the_next_one() -> None:
    manager = _manager(_gated(_open_gate(), ReindexResult(migrated=1, skipped=0, failed=0)))
    first = schedule_memory_reindex(manager)
    await _finished(first)

    second = schedule_memory_reindex(manager)
    await _finished(second)

    assert second is not first
    assert manager.reindex_from_orphans.await_count == 2


async def test_an_unexpected_error_fails_the_run_and_frees_the_slot() -> None:
    async def broken(**_kwargs: object) -> ReindexResult:
        raise RuntimeError("vector store offline")

    run = schedule_memory_reindex(_manager(broken))
    await _finished(run)

    assert run.state is ReindexRunState.FAILED
    assert run.result is None
    assert schedule_memory_reindex(_manager(_gated(_open_gate(), ReindexResult(0, 0, 0)))) is not run


def test_no_run_yet_reads_as_none() -> None:
    assert get_memory_reindex_run() is None
