"""Reaping a shell that leads its own process group (the default for a local, unsandboxed shell).

One group signal stops everything that stayed in the group. Two things escape it and are covered here: a descendant that
started its own session (``setsid``), which is no longer in the group, and a shell that is already gone whose PID the
operating system may have handed to an unrelated process group.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import subprocess
import sys
from collections.abc import AsyncIterator
from types import SimpleNamespace
from typing import cast

import pytest

from myrm_agent_harness.toolkits.code_execution.session.process_tree import kill_process_tree
from tests.support.marked_processes import kill_marked, process_alive, wait_until

_ESCAPE = "import os, signal, time; os.setsid(); {ignore}time.sleep({marker})"


@contextlib.asynccontextmanager
async def _shell_with_escapee(marker: str, *, ignore_terminate: bool) -> AsyncIterator[asyncio.subprocess.Process]:
    """A shell in its own group whose background child left that group; leftovers are removed on failure."""
    ignore = "signal.signal(signal.SIGTERM, signal.SIG_IGN); " if ignore_terminate else ""
    escapee = _ESCAPE.format(ignore=ignore, marker=marker)
    process = await asyncio.create_subprocess_exec(
        "bash",
        "-c",
        f"{shlex.quote(sys.executable)} -c {shlex.quote(escapee)} & wait",
        start_new_session=True,
    )
    assert os.getpgid(process.pid) == process.pid, "the shell must lead its own group"
    try:
        await wait_until(lambda: process_alive(marker))
        yield process
    finally:
        kill_marked(marker)
        with contextlib.suppress(ProcessLookupError):
            process.kill()
        await process.wait()


@pytest.mark.asyncio
async def test_a_descendant_that_started_its_own_session_is_stopped_with_the_shell() -> None:
    marker = "4721.01"
    async with _shell_with_escapee(marker, ignore_terminate=False) as process:
        await kill_process_tree(process, is_windows=False, grace_period=2.0)

        assert process.returncode is not None
        assert not process_alive(marker)


@pytest.mark.asyncio
async def test_an_escaped_descendant_that_ignores_terminate_is_killed_after_the_grace_period() -> None:
    marker = "4721.02"
    async with _shell_with_escapee(marker, ignore_terminate=True) as process:
        await kill_process_tree(process, is_windows=False, grace_period=0.3)

        assert process.returncode is not None
        assert not process_alive(marker)


@pytest.mark.asyncio
async def test_a_shell_that_is_already_reaped_never_signals_the_group_its_pid_now_belongs_to() -> None:
    marker = "4721.03"
    # Another session's group leader: what a recycled PID of our dead shell would now point at.
    bystander = subprocess.Popen(["sleep", marker], start_new_session=True)
    try:
        await wait_until(lambda: process_alive(marker))

        async def _already_reaped() -> int:
            return 0

        dead_shell = SimpleNamespace(pid=bystander.pid, returncode=0, wait=_already_reaped)
        await kill_process_tree(cast(asyncio.subprocess.Process, dead_shell), is_windows=False, grace_period=0.3)
        await asyncio.sleep(0.3)

        assert bystander.poll() is None, "the unrelated group must be left alone"
    finally:
        bystander.kill()
        bystander.wait()
