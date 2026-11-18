"""A job that prints without end costs the host bounded memory, bounded disk and a short loop stall, and a kill settles it.

A program that prints as fast as it is read is the worst case for the output pipeline. Each job here gets a block of
1,000 lines whenever the reader has taken the last one, which is what an OS pipe does to a producer (it blocks when it
is full), for ``_FLOOD_SECONDS``.

The loop stall is the CPU time the loop thread spends between two beats of a 10 ms timer, not the wall-clock lateness of
the beat: on a busy host the wall clock also counts the time the thread was descheduled, which says nothing about the
pipeline. Run with ``-m performance -s`` to see the numbers.
"""

from __future__ import annotations

import asyncio
import gc
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from unittest.mock import patch

import psutil
import pytest

from myrm_agent_harness.agent.context_management.infra.evicted import MAX_STORED_CHARS
from myrm_agent_harness.agent.meta_tools.bash._background.registry import BackgroundProcessRegistry
from myrm_agent_harness.agent.meta_tools.bash._background.types import OUTPUT_RING_LINES
from myrm_agent_harness.toolkits.code_execution.executors.models import AsyncProcessProtocol
from tests.agent.meta_tools.bash.fake_background_proc import FakeOutputPipe, FakeProc

pytestmark = [pytest.mark.performance, pytest.mark.usefixtures("workspace")]

_FLOOD_SECONDS = 12.0
_BEAT_SECONDS = 0.01
_BLOCK_LINES = 1_000
_BLOCK = "".join(f"flood line {i} " + "x" * 48 + "\n" for i in range(_BLOCK_LINES)).encode()
_FIRST_PID = 74_000
_KILL_TARGET = "myrm_agent_harness.agent.meta_tools.bash._background.termination.kill_spawned_group"

# What the pipeline may cost; each is far above what the flood measures, so that a host's noise cannot trip it and a
# regression of an order of magnitude does.
_RSS_GROWTH_BUDGET = 10 * 1024 * 1024
_LOG_SLACK = 512  # the cap marker line that follows the stored text
_SETTLE_BUDGET_SECONDS = 0.1
_BUSY_BUDGET_SECONDS = {1: 0.15, 5: 0.30}


@dataclass(frozen=True)
class _Flood:
    """What a flood of ``jobs`` concurrent jobs cost and left behind."""

    busy_p99: float
    busy_max: float
    beats: int
    rss_growth: int
    log_sizes: list[int]
    settle_seconds: list[float]
    last_lines: list[str]
    dropped: list[bool]
    lines_read: list[int]


async def _feed(pipe: FakeOutputPipe, stop: asyncio.Event) -> None:
    while not stop.is_set():
        if pipe.backlog == 0:
            pipe.feed(_BLOCK)
        await asyncio.sleep(0)


async def _beat(busy: list[float], stop: asyncio.Event) -> None:
    while not stop.is_set():
        before = time.thread_time()
        await asyncio.sleep(_BEAT_SECONDS)
        busy.append(time.thread_time() - before)


def _ends_the_process(procs: dict[int, FakeProc]) -> Callable[[int, int], None]:
    def end(pid: int, sig: int) -> None:
        procs[pid].finish(-sig)

    return end


async def _flood(jobs: int, workspace: Path) -> _Flood:
    registry = BackgroundProcessRegistry()
    procs: dict[int, FakeProc] = {}
    pipes: dict[int, FakeOutputPipe] = {}
    for k in range(jobs):
        pid = _FIRST_PID + k
        pipes[pid] = FakeOutputPipe(hold_open=True)
        procs[pid] = FakeProc(pid=pid, stdout=[], stdout_pipe=pipes[pid])
        await registry.register(cast(AsyncProcessProtocol, procs[pid]), command="flood", session_id=f"flood-{k}")

    process = psutil.Process()
    gc.collect()
    baseline = peak = process.memory_info().rss
    stop = asyncio.Event()
    busy: list[float] = []
    beat = asyncio.create_task(_beat(busy, stop))
    feeders = [asyncio.create_task(_feed(pipe, stop)) for pipe in pipes.values()]
    deadline = time.monotonic() + _FLOOD_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(0.25)
        peak = max(peak, process.memory_info().rss)
    stop.set()
    await asyncio.gather(beat, *feeders)

    settle: list[float] = []
    with patch(_KILL_TARGET, side_effect=_ends_the_process(procs)):
        for pid in procs:
            reader = registry._entries[pid].reader_task
            assert reader is not None
            started = time.perf_counter()
            assert await registry.kill(pid, force=False)
            await asyncio.wait_for(reader, timeout=5)
            settle.append(time.perf_counter() - started)

    tails = {pid: registry.get_output(pid, max_lines=OUTPUT_RING_LINES) for pid in procs}
    ordered = sorted(busy)
    return _Flood(
        busy_p99=ordered[int(len(ordered) * 0.99)],
        busy_max=ordered[-1],
        beats=len(ordered),
        rss_growth=peak - baseline,
        log_sizes=[path.stat().st_size for path in sorted(workspace.rglob("output_*.txt"))],
        settle_seconds=settle,
        last_lines=[tail["stdout"][-1] for tail in tails.values()],
        dropped=[tail["dropped"] for tail in tails.values()],
        lines_read=[registry._entries[pid].stdout_total for pid in procs],
    )


def _report(jobs: int, flood: _Flood) -> None:
    print(
        f"\nflood x{jobs} for {_FLOOD_SECONDS:.0f}s: lines per job {flood.lines_read}; "
        f"loop busy between beats p99 {flood.busy_p99 * 1000:.1f} ms, max {flood.busy_max * 1000:.1f} ms "
        f"({flood.beats} beats); rss growth {flood.rss_growth / 1024:.0f} KiB; "
        f"log sizes {[size // 1000 for size in flood.log_sizes]} KB; "
        f"kill to settled {[round(s * 1000, 1) for s in flood.settle_seconds]} ms"
    )


@pytest.mark.parametrize("jobs", [1, 5])
@pytest.mark.asyncio
async def test_a_flood_costs_bounded_memory_disk_and_loop_time_and_a_kill_settles_it(
    jobs: int, workspace: Path
) -> None:
    flood = await _flood(jobs, workspace)
    _report(jobs, flood)

    assert flood.beats >= 50, "the loop must beat often enough for the percentile to mean something"
    assert flood.busy_p99 < _BUSY_BUDGET_SECONDS[jobs]
    assert flood.rss_growth < _RSS_GROWTH_BUDGET
    assert len(flood.log_sizes) == jobs
    assert all(size <= MAX_STORED_CHARS + _LOG_SLACK for size in flood.log_sizes)
    assert all(settled < _SETTLE_BUDGET_SECONDS for settled in flood.settle_seconds)
    # The job stays readable: the tail is the newest lines, and the reader says the oldest are gone.
    assert all(line.startswith(f"flood line {_BLOCK_LINES - 1} ") for line in flood.last_lines)
    assert all(flood.dropped)
    assert all(count > OUTPUT_RING_LINES for count in flood.lines_read)
