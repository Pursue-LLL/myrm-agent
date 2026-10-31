"""A cancelled request or a deadline stops the Python script its subprocess is running, and what the script started."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess import run_python_subprocess
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_SETTLE_S = 10
_MAX_OUTPUT_BYTES = 5 * 1024 * 1024
_SCRIPT = "hold_4711_8.py"
_CHILD = "time.sleep(4754)"
# The script exits at once; the child it started inherits the pipes and keeps them open.
_START_CHILD_AND_EXIT = f"import subprocess, sys\nsubprocess.Popen([sys.executable, '-c', 'import time; {_CHILD}'])\n"


@pytest.fixture(autouse=True)
def _no_native_sandbox() -> Iterator[None]:
    """The sandbox wrapper is irrelevant to the stop path and needs host-specific read grants."""
    with patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        return_value=(None, SandboxStatus(enabled=False, provider_name="null", reason="test")),
    ):
        yield
    kill_marked(_SCRIPT)
    kill_marked(_CHILD)


async def _run(script: Path, token: CancellationToken | None, timeout: int = 60) -> asyncio.Task[object]:
    context = ExecutionContext(code="", cancel_token=token)
    return asyncio.create_task(
        run_python_subprocess(
            script_path=script,
            timeout=timeout,
            python_executable=sys.executable,
            cwd=script.parent,
            context=context,
            max_output_bytes=_MAX_OUTPUT_BYTES,
        )
    )


@pytest.mark.asyncio
async def test_cancelling_the_token_stops_the_running_script(tmp_path: Path) -> None:
    script = tmp_path / _SCRIPT
    script.write_text("import time\nprint('started', flush=True)\ntime.sleep(4711)\n")
    token = CancellationToken("req-1")

    running = await _run(script, token)
    await wait_until(lambda: process_alive(_SCRIPT))
    token.cancel(CancelReason.USER_CANCELLED)
    async with asyncio.timeout(_SETTLE_S):
        result = await running

    assert result.success is False  # type: ignore[attr-defined]
    assert "cancelled" in (result.error or "").lower()  # type: ignore[attr-defined]
    assert not process_alive(_SCRIPT)


@pytest.mark.asyncio
async def test_a_token_that_is_never_cancelled_changes_nothing(tmp_path: Path) -> None:
    script = tmp_path / _SCRIPT
    script.write_text("print('done')\n")

    running = await _run(script, CancellationToken("req-1"))
    result = await asyncio.wait_for(running, _SETTLE_S)

    assert result.success is True  # type: ignore[attr-defined]
    assert "done" in result.stdout  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_a_script_that_times_out_is_still_reported_as_a_timeout(tmp_path: Path) -> None:
    script = tmp_path / _SCRIPT
    script.write_text("import time\ntime.sleep(4711)\n")

    running = await _run(script, CancellationToken("req-1"), timeout=1)
    result = await asyncio.wait_for(running, _SETTLE_S)

    assert result.success is False  # type: ignore[attr-defined]
    assert "timed out" in (result.error or "").lower()  # type: ignore[attr-defined]
    assert not process_alive(_SCRIPT)


@pytest.mark.asyncio
async def test_a_script_that_times_out_takes_down_what_it_left_running(tmp_path: Path) -> None:
    script = tmp_path / _SCRIPT
    script.write_text(_START_CHILD_AND_EXIT)

    running = await _run(script, CancellationToken("req-1"), timeout=2)
    result = await asyncio.wait_for(running, _SETTLE_S)

    assert "timed out" in (result.error or "").lower()  # type: ignore[attr-defined]
    assert not process_alive(_CHILD)


@pytest.mark.asyncio
async def test_cancelling_the_token_takes_down_what_the_script_left_running(tmp_path: Path) -> None:
    script = tmp_path / _SCRIPT
    script.write_text(_START_CHILD_AND_EXIT)
    token = CancellationToken("req-1")

    running = await _run(script, token)
    await wait_until(lambda: process_alive(_CHILD) and not process_alive(_SCRIPT))
    token.cancel(CancelReason.USER_CANCELLED)
    async with asyncio.timeout(_SETTLE_S):
        result = await running

    assert "cancelled" in (result.error or "").lower()  # type: ignore[attr-defined]
    assert not process_alive(_CHILD)
