"""Unit tests for consume.py background output reading and progress throttling."""

from __future__ import annotations

from collections import deque
from typing import cast

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background.consume import (
    BackgroundRegistryEntry,
    consume_background_entry,
)
from myrm_agent_harness.agent.meta_tools.bash._background.types import (
    BackgroundProcessInfo,
)
from myrm_agent_harness.toolkits.code_execution.executors.models import (
    AsyncProcessProtocol,
)
from tests.agent.meta_tools.bash.fake_background_proc import FakeProc


@pytest.mark.asyncio
async def test_progress_throttle_and_terminal_penetration() -> None:
    """10Hz throttle smooths high-frequency bursts while 100% penetrates immediately."""
    emitted: list[dict[str, object]] = []

    async def _on_progress(_info: BackgroundProcessInfo, payload: dict[str, object]) -> None:
        emitted.append(payload)

    # 50 high-frequency lines emitted in a burst, followed by a 100% completion marker
    lines = [f'MYRM_PROGRESS {{"percent": {i}, "message": "Step {i}"}}\n'.encode() for i in range(1, 50)]
    lines.append(b'MYRM_PROGRESS {"percent": 100, "message": "Completed"}\n')

    proc = FakeProc(pid=29001, stdout=lines, stderr=[])
    proc.finish(0)
    info = BackgroundProcessInfo(
        job_id="job-29001",
        pid=29001,
        command="batch.sh",
        session_id="test-sess",
        started_at=0.0,
        status="running",
    )
    entry = BackgroundRegistryEntry(
        info=info,
        proc=cast(AsyncProcessProtocol, proc),
        stdout_buffer=deque(),
        stderr_buffer=deque(),
        progress_listener=_on_progress,
    )

    reaped: list[int] = []

    def _schedule_reap(pid: int) -> None:
        reaped.append(pid)

    def _snapshot(e: BackgroundRegistryEntry) -> BackgroundProcessInfo:
        return e.info

    await consume_background_entry(
        entry,
        snapshot=_snapshot,
        schedule_reap=_schedule_reap,
    )

    # 1. High frequency burst must be throttled (significantly fewer than 50 events)
    assert len(emitted) < 20, f"Expected throttled progress events, got {len(emitted)}"
    # 2. First event must arrive
    assert emitted[0]["progress"] == 1
    # 3. 100% terminal event must penetrate immediately and be the last emitted event
    assert emitted[-1]["progress"] == 100
    assert emitted[-1]["message"] == "Completed"
    # 4. In-memory snapshot on registry entry must be 100% up-to-date
    assert entry.info.last_progress is not None
    assert entry.info.last_progress["progress"] == 100
    assert entry.info.last_progress["message"] == "Completed"


@pytest.mark.asyncio
async def test_trailing_progress_flush_on_non_100_percent_exit() -> None:
    """Non-100% progress trapped inside the 100ms window must be flushed on exit."""
    emitted: list[dict[str, object]] = []

    async def _on_progress(_info: BackgroundProcessInfo, payload: dict[str, object]) -> None:
        emitted.append(payload)

    # 10 lines emitted in zero delay, ending with 98% (not 100%, no checkpoint)
    lines = [f'MYRM_PROGRESS {{"percent": {i}, "message": "Step {i}"}}\n'.encode() for i in range(1, 10)]
    lines.append(b'MYRM_PROGRESS {"percent": 98, "message": "Aborted near finish"}\n')

    proc = FakeProc(pid=29002, stdout=lines, stderr=[])
    proc.finish(1)
    info = BackgroundProcessInfo(
        job_id="job-29002",
        pid=29002,
        command="abort.sh",
        session_id="test-sess-2",
        started_at=0.0,
        status="running",
    )
    entry = BackgroundRegistryEntry(
        info=info,
        proc=cast(AsyncProcessProtocol, proc),
        stdout_buffer=deque(),
        stderr_buffer=deque(),
        progress_listener=_on_progress,
    )

    await consume_background_entry(
        entry,
        snapshot=lambda e: e.info,
        schedule_reap=lambda _p: None,
    )

    # The 98% tail progress must be delivered via trailing flush despite <100ms gap
    assert emitted[-1]["progress"] == 98
    assert emitted[-1]["message"] == "Aborted near finish"
    assert entry.info.exit_code == 1
