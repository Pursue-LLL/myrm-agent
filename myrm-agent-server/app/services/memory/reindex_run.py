"""The memory reindex run: single flight plus the state the Settings page polls.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: orphan scan + migration into the current embedding model)

[OUTPUT]
- ReindexRunState / ReindexRun / ReindexOutcome: lifecycle states, live state of the run (done/total) and its outcome
- ReindexBusyError: a run into another embedding model is still in flight
- schedule_memory_reindex: start the run in the background, or join the one in flight for the same model
- get_memory_reindex_run: the latest run

[POS]
Re-embedding the memories of a previous model goes through the user's embedding provider and takes minutes
on a large store, longer than a request may wait; a second run at the same time would only pay for the same
memories twice. A run writes into the collections of the model it started with, so only a request for that
same model may join it; joining from another model would report memories as migrated that never reached the
model now in use. The registry lives in memory: it is transient progress of this single-process server, and a
run cut short by a restart is simply started again, because migration skips what is already in place.
The latest run stays after it ends, until the next run replaces it.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum

from myrm_agent_harness.toolkits.memory import MemoryManager

logger = logging.getLogger(__name__)


class ReindexRunState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class ReindexOutcome:
    """Memories moved to the current model / already there / that could not be moved."""

    migrated: int
    skipped: int
    failed: int


class ReindexBusyError(RuntimeError):
    """A run into another embedding model is still in flight."""


@dataclass(slots=True)
class ReindexRun:
    # The embedding model whose collections this run writes into.
    embedding_model: str
    state: ReindexRunState = ReindexRunState.RUNNING
    done: int = 0
    total: int = 0
    # A finished run can still carry failed memories; only an unexpected error leaves it without a result.
    result: ReindexOutcome | None = None
    # The event loop keeps no strong reference to a task nobody awaits.
    task: asyncio.Task[None] | None = None

    def on_progress(self, done: int, total: int, _phase: str) -> None:
        self.done = done
        self.total = total


_latest_run: ReindexRun | None = None


def schedule_memory_reindex(manager: MemoryManager) -> ReindexRun:
    """Start a background run, or hand back the one in flight for the same embedding model.

    Nothing is awaited between the check and the claim, so two callers cannot both start a run.

    Raises:
        ReindexBusyError: A run into a different embedding model has not finished yet.
    """
    global _latest_run
    embedding_model = manager.config.embedding_model
    if _latest_run is not None and _latest_run.state is ReindexRunState.RUNNING:
        if _latest_run.embedding_model != embedding_model:
            raise ReindexBusyError(f"A migration into {_latest_run.embedding_model} is still running")
        return _latest_run
    run = ReindexRun(embedding_model=embedding_model)
    _latest_run = run
    run.task = asyncio.create_task(_execute(run, manager))
    return run


def get_memory_reindex_run() -> ReindexRun | None:
    return _latest_run


async def _execute(run: ReindexRun, manager: MemoryManager) -> None:
    try:
        result = await manager.reindex_from_orphans(progress_cb=run.on_progress)
        run.result = ReindexOutcome(migrated=result.migrated, skipped=result.skipped, failed=result.failed)
    except Exception:
        logger.exception("Memory reindex failed")
        run.state = ReindexRunState.FAILED
        return
    run.state = ReindexRunState.SUCCEEDED
