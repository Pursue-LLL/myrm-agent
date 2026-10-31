"""A command hook keeps a bounded amount of what it writes, and what it started is stopped at the deadline or a cancel."""

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
from myrm_agent_harness.agent.hooks.command_runner import MAX_HOOK_OUTPUT_CHARS
from myrm_agent_harness.core.security.bounded_communicate import DEFAULT_MAX_OUTPUT_BYTES
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_FLOOD_MARKER = "hook_flood_4711"
_SLEEP_MARKER = "sleep 4751"
# The shell stays alive next to its sleeper, or exits and leaves the sleeper holding the hook's pipes.
_SLEEPER_BODIES = pytest.mark.parametrize(
    "body", ["sleep 4751; echo done", "sleep 4751 & echo started"], ids=["after_the_sleeper", "background_sleeper"]
)


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
async def test_output_past_what_the_pipe_keeps_is_cut_to_the_result_cap_and_the_hook_still_succeeds(
    tmp_path: Path,
) -> None:
    command = _script(tmp_path, f"head -c {DEFAULT_MAX_OUTPUT_BYTES + 2_000_000} /dev/zero | tr '\\0' x")

    result = await asyncio.wait_for(_fire(command), timeout=30)

    assert result.success is True
    assert len(result.output) <= MAX_HOOK_OUTPUT_CHARS


@pytest.mark.asyncio
async def test_a_failing_hook_with_long_output_reports_its_first_and_last_lines_within_the_cap(tmp_path: Path) -> None:
    command = _script(
        tmp_path,
        "echo 'FIRST: a.py:1: E501 line too long'\n"
        'for i in $(seq 1 5000); do echo "a.py:$i: E501 line too long (120 > 100)"; done\n'
        "echo 'LAST: Found 5000 errors.'\n"
        "exit 1",
    )

    result = await asyncio.wait_for(_fire(command), timeout=30)

    assert result.success is False
    assert len(result.output) <= MAX_HOOK_OUTPUT_CHARS
    assert result.reason == result.output
    assert result.output.startswith("FIRST: ")
    assert result.output.endswith("LAST: Found 5000 errors.")


@pytest.mark.asyncio
async def test_output_within_the_cap_is_reported_whole(tmp_path: Path) -> None:
    command = _script(tmp_path, "echo out; echo err >&2")

    result = await asyncio.wait_for(_fire(command), timeout=30)

    assert result.output == "out\nerr"


@pytest.mark.asyncio
async def test_a_payload_larger_than_the_pipe_buffer_reaches_the_hook_through_stdin(tmp_path: Path) -> None:
    payload: dict[str, object] = {"blob": "x" * 300_000}
    command = _script(tmp_path, "wc -c")

    result = await asyncio.wait_for(_fire(command, timeout=15, payload=payload), timeout=30)

    assert result.success is True
    assert int(result.output) == len(json.dumps(payload, default=str, ensure_ascii=True))


@pytest.mark.asyncio
@_SLEEPER_BODIES
async def test_a_hook_is_stopped_at_its_deadline_together_with_everything_it_started(tmp_path: Path, body: str) -> None:
    command = _script(tmp_path, body)
    started = time.monotonic()

    result = await asyncio.wait_for(_fire(command, timeout=2), timeout=30)

    assert "timed out" in result.reason
    # Left running, what the hook started keeps its pipes open and the host waits out the whole drain period for them.
    assert time.monotonic() - started < 4.5
    assert not process_alive(_SLEEP_MARKER)


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["exec sleep 4751", "sleep 4751; echo done", "sleep 4751 & echo started"])
async def test_cancelling_the_run_stops_the_hook_and_what_it_started(tmp_path: Path, body: str) -> None:
    command = _script(tmp_path, body)
    running = asyncio.create_task(_fire(command, timeout=60))
    await wait_until(lambda: process_alive(_SLEEP_MARKER))

    running.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(running, timeout=15)

    assert not process_alive(_SLEEP_MARKER)
