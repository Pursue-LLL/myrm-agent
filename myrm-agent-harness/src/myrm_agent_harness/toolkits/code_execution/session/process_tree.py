"""Kill a shell and everything it started.

[INPUT]
- psutil (POS: process tree inspection for shells that share the server's process group)

[OUTPUT]
kill_process_tree: stop a process and its whole tree, escalating from terminate to kill after a grace period.

[POS]
Process-tree reaper for persistent shells. A shell with its own process group is stopped with one group signal;
a shell launched under a native sandbox shares the server's group, which must never be signalled, so its
descendants are stopped one by one. Descendants are listed while the shell is alive so a child that left the group
(``setsid``) is still stopped, and a shell that has already been reaped is never signalled by PID because the
operating system may have given that PID to an unrelated process group. Used by the timeout, cancel and close paths
so none leaves an orphan behind.
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


async def _reap_survivors(descendants: list[psutil.Process], grace_period: float) -> None:
    """Kill whatever from the pre-signal snapshot is still running once the grace period has passed."""
    _, survivors = await asyncio.to_thread(psutil.wait_procs, descendants, grace_period)
    for child in survivors:
        _signal(child.kill)


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
    await _reap_survivors(descendants, grace_period)


async def _terminate_own_group(process: asyncio.subprocess.Process, pgid: int, grace_period: float) -> None:
    """Stop a shell that leads its own group with one group signal, then sweep the descendants that left the group."""
    # A descendant that called setsid is no longer in ``pgid`` and would outlive the group signal.
    descendants = await asyncio.to_thread(_descendants, process.pid)
    # The group may be gone since the snapshot; the descendants that left it still have to be reaped below.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, signal.SIGTERM)
    for child in descendants:
        _signal(child.terminate)
    try:
        await asyncio.wait_for(process.wait(), timeout=grace_period)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pgid, signal.SIGKILL)
    await _reap_survivors(descendants, grace_period)


async def kill_process_tree(
    process: asyncio.subprocess.Process,
    is_windows: bool,
    grace_period: float = 2.0,
) -> None:
    """Kill a process and its entire process tree; a process that was already reaped is left alone."""
    pid = process.pid
    if pid is None:
        return

    # Reaped means the PID is free for reuse: signalling it (or its group) could hit an unrelated process.
    if process.returncode is not None:
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
            await _terminate_own_group(process, pgid, grace_period)
    except (ProcessLookupError, OSError):
        pass
