"""A cancelled request stops the Python script its subprocess is running (the script and its workers die)."""

from __future__ import annotations

import asyncio
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest

from myrm_agent_harness.toolkits.code_execution.executors.local._python_subprocess import run_python_subprocess
from myrm_agent_harness.toolkits.code_execution.executors.models import ExecutionContext
from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import SandboxStatus
from myrm_agent_harness.utils.runtime.cancellation import CancellationToken, CancelReason

_SETTLE_S = 10
_SCRIPT = "hold_4711_8.py"


def _alive(marker: str) -> bool:
    return subprocess.run(["pgrep", "-f", marker], capture_output=True).returncode == 0


async def _wait_until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(_SETTLE_S):
        while not condition():
            await asyncio.sleep(0.05)


@pytest.fixture(autouse=True)
def _no_native_sandbox() -> Iterator[None]:
    """The sandbox wrapper is irrelevant to the stop path and needs host-specific read grants."""
    with patch(
        "myrm_agent_harness.toolkits.code_execution.sandbox.detect_sandbox_provider",
        return_value=(None, SandboxStatus(enabled=False, provider_name="null", reason="test")),
    ):
        yield
    subprocess.run(["pkill", "-f", _SCRIPT], capture_output=True)


async def _run(script: Path, token: CancellationToken | None, timeout: int = 60) -> asyncio.Task[object]:
    context = ExecutionContext(code="", cancel_token=token)
    return asyncio.create_task(
        run_python_subprocess(
            script_path=script,
            timeout=timeout,
            python_executable=sys.executable,
            cwd=script.parent,
            context=context,
        )
    )


@pytest.mark.asyncio
async def test_cancelling_the_token_stops_the_running_script(tmp_path: Path) -> None:
    script = tmp_path / _SCRIPT
    script.write_text("import time\nprint('started', flush=True)\ntime.sleep(4711)\n")
    token = CancellationToken("req-1")

    running = await _run(script, token)
    await _wait_until(lambda: _alive(_SCRIPT))
    token.cancel(CancelReason.USER_CANCELLED)
    async with asyncio.timeout(_SETTLE_S):
        result = await running

    assert result.success is False  # type: ignore[attr-defined]
    assert "cancelled" in (result.error or "").lower()  # type: ignore[attr-defined]
    assert not _alive(_SCRIPT)


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
    assert not _alive(_SCRIPT)
