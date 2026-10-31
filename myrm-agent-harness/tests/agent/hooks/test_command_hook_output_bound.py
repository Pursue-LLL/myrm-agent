"""A command hook keeps a bounded amount of what it writes, and its process is stopped at the deadline or a cancel."""

from __future__ import annotations

import asyncio
import json
import time
import tracemalloc
from collections.abc import Iterator
from pathlib import Path

import pytest

from myrm_agent_harness.agent.hooks import (
    CommandHookDefinition,
    HookEvent,
    HookExecutor,
    HookRegistry,
    HookResult,
)
from myrm_agent_harness.core.security.bounded_communicate import DEFAULT_MAX_OUTPUT_BYTES
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_FLOOD_MARKER = "hook_flood_4711"
_SLEEP_MARKER = "sleep 4711"


@pytest.fixture(autouse=True)
def _reap_hook_processes() -> Iterator[None]:
    yield
    kill_marked(_FLOOD_MARKER)
    kill_marked(_SLEEP_MARKER)


def _script(tmp_path: Path, body: str) -> str:
    path = tmp_path / "hook.sh"
    path.write_text(f"#!/bin/bash\n{body}\n")
    path.chmod(0o755)
    return str(path)


async def _fire(command: str, *, timeout: int = 30, payload: dict[str, object] | None = None) -> HookResult:
    registry = HookRegistry()
    registry.register(HookEvent.SESSION_START, CommandHookDefinition(command=command, timeout_seconds=timeout))
    aggregated = await HookExecutor(registry).execute(HookEvent.SESSION_START, payload or {})
    return aggregated.results[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [f"exec yes {_FLOOD_MARKER}", f"exec yes {_FLOOD_MARKER} >&2"],
    ids=["stdout", "stderr"],
)
async def test_a_hook_that_never_stops_writing_is_stopped_at_its_deadline_without_filling_memory(
    tmp_path: Path, body: str
) -> None:
    command = _script(tmp_path, body)
    tracemalloc.start()
    tracemalloc.reset_peak()
    started = time.monotonic()
    try:
        result = await asyncio.wait_for(_fire(command, timeout=2), timeout=30)
        peak_bytes = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()

    assert result.success is False
    assert "timed out" in result.reason
    assert time.monotonic() - started < 8
    assert not process_alive(_FLOOD_MARKER)
    # Without a cap the host keeps every byte the hook wrote during the two seconds (hundreds of MB).
    assert peak_bytes < 40 * 1024 * 1024


@pytest.mark.asyncio
async def test_output_over_the_cap_is_cut_and_the_hook_still_succeeds(tmp_path: Path) -> None:
    command = _script(tmp_path, "head -c 7000000 /dev/zero | tr '\\0' x")

    result = await asyncio.wait_for(_fire(command), timeout=30)

    assert result.success is True
    assert result.output == "x" * DEFAULT_MAX_OUTPUT_BYTES


@pytest.mark.asyncio
async def test_a_payload_larger_than_the_pipe_buffer_reaches_the_hook_through_stdin(tmp_path: Path) -> None:
    payload: dict[str, object] = {"blob": "x" * 300_000}
    command = _script(tmp_path, "wc -c")

    result = await asyncio.wait_for(_fire(command, timeout=15, payload=payload), timeout=30)

    assert result.success is True
    assert int(result.output) == len(json.dumps(payload, default=str, ensure_ascii=True))


@pytest.mark.asyncio
async def test_cancelling_the_run_stops_the_hook_process(tmp_path: Path) -> None:
    command = _script(tmp_path, "exec sleep 4711")
    running = asyncio.create_task(_fire(command, timeout=60))
    await wait_until(lambda: process_alive(_SLEEP_MARKER))

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(running, timeout=15)

    assert not process_alive(_SLEEP_MARKER)
