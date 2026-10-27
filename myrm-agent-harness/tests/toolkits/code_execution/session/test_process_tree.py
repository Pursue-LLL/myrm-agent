"""Reaping a shell that shares the server's process group (a natively sandboxed shell).

The group must never be signalled, so the shell's descendants are stopped one by one. These tests start the shell
the same way, in the test process's own group, so the path is exercised on every platform rather than only where a
native sandbox provider exists.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
from collections.abc import AsyncIterator
from unittest.mock import MagicMock, patch

import psutil
import pytest

from myrm_agent_harness.toolkits.code_execution.session import process_tree
from myrm_agent_harness.toolkits.code_execution.session.process_tree import kill_process_tree
from tests.support.marked_processes import kill_marked, process_alive, wait_until


@contextlib.asynccontextmanager
async def _shell(script: str, marker: str) -> AsyncIterator[asyncio.subprocess.Process]:
    """A shell in this process's group running ``script``; whatever a failing test leaves behind is removed."""
    process = await asyncio.create_subprocess_exec("bash", "-c", script)
    assert os.getpgid(process.pid) == os.getpgid(os.getpid()), "the shell must share the test process's group"
    try:
        await wait_until(lambda: process_alive(marker))
        yield process
    finally:
        kill_marked(marker)
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()


@pytest.mark.asyncio
async def test_the_shell_and_the_command_it_is_blocked_on_both_end() -> None:
    marker = "sleep 4713.11"
    async with _shell(f"{marker}; echo never", marker) as process:
        await kill_process_tree(process, is_windows=False, grace_period=2.0)

        assert process.returncode is not None
        assert not process_alive(marker)


@pytest.mark.asyncio
async def test_a_command_that_ignores_terminate_is_killed_after_the_grace_period() -> None:
    marker = "sleep 4713.12"
    async with _shell(f"trap '' TERM; {marker}; echo never", marker) as process:
        await kill_process_tree(process, is_windows=False, grace_period=0.3)

        assert process.returncode is not None
        assert not process_alive(marker)


@pytest.mark.asyncio
async def test_descendants_are_reaped_even_when_the_shell_exited_after_the_snapshot() -> None:
    marker = "sleep 4713.13"
    async with _shell(f"trap '' TERM; {marker}; echo never", marker) as process:
        sleeper = psutil.Process(process.pid).children(recursive=True)[0]
        gone = MagicMock(wraps=process)
        gone.pid = process.pid
        gone.terminate.side_effect = ProcessLookupError
        gone.kill.side_effect = ProcessLookupError
        with patch.object(process_tree, "_descendants", return_value=[sleeper]):
            await kill_process_tree(gone, is_windows=False, grace_period=0.3)

        assert not process_alive(marker)
