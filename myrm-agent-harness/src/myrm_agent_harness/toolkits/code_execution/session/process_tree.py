"""Kill a shell and everything it started.

[INPUT]
- psutil (POS: process tree inspection for shells that share the server's process group)

[OUTPUT]
kill_process_tree: stop a process and its whole tree, escalating from terminate to kill after a grace period.

[POS]
Process-tree reaper for persistent shells. A shell with its own process group is stopped with one group signal;
a shell launched under a native sandbox shares the server's group, which must never be signalled, so its
descendants are stopped one by one. Used by the timeout, cancel and close paths so none leaves an orphan behind.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
from collections.abc import Callable

import psutil


def _descendants(pid: int) -> list[psutil.Process]:
    try:
        return psutil.Process(pid).children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def _signal(action: Callable[[], None]) -> None:
    """Send one signal; a process that is already gone, or that we may not signal, is not an error."""
    with contextlib.suppress(psutil.Error):
        action()


async def _terminate_in_shared_group(process: asyncio.subprocess.Process, grace_period: float) -> None:
    """Stop the shell and its descendants without signalling the process group the server itself lives in."""
    # Taken while the shell is alive: once it dies its children re-parent to init and the tree is lost.
    descendants = await asyncio.to_thread(_descendants, process.pid)
    # Children first: a shell blocked on a foreground command only handles its own SIGTERM after that command ends.
    for child in descendants:
        _signal(child.terminate)
    # The shell may have exited since the snapshot; its descendants still have to be reaped below.
    with contextlib.suppress(ProcessLookupError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=grace_period)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            process.kill()
    _, survivors = await asyncio.to_thread(psutil.wait_procs, descendants, grace_period)
    for child in survivors:
        _signal(child.kill)


async def kill_process_tree(
    process: asyncio.subprocess.Process,
    is_windows: bool,
    grace_period: float = 2.0,
) -> None:
    """Kill a process and its entire process tree."""
    pid = process.pid
    if pid is None:
        return

    if is_windows:
        try:
            p = await asyncio.create_subprocess_exec(
                "taskkill",
                "/F",
                "/T",
                "/PID",
                str(pid),
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            await p.wait()
        except Exception:
            process.kill()
        return

    try:
        pgid = os.getpgid(pid)
        if pgid == os.getpgid(os.getpid()):
            await _terminate_in_shared_group(process, grace_period)
        else:
            os.killpg(pgid, signal.SIGTERM)
            try:
                await asyncio.wait_for(process.wait(), timeout=grace_period)
            except TimeoutError:
                os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError):
        pass
