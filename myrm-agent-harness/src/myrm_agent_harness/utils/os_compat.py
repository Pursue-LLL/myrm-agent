"""Cross-platform OS compatibility layer.

[INPUT]
- sys
- os
- signal
- subprocess

[OUTPUT]
- IS_WIN: Whether the host operating system is Windows.
- SIGKILL: The signal that force-kills a process tree (SIGTERM on Windows, which has no SIGKILL).
- get_process_group_kwargs: Subprocess kwargs for creating process groups.
- kill_process_group: Safely kill a process group tree.
- kill_spawned_group: Kill the group a child was started in, even once the child itself has exited.
- terminate_process_graceful: SIGTERM then wait then SIGKILL for a process tree.

[POS]
Provides unified abstractions for POSIX/Windows differences (process groups)
to ensure 100% native execution across all platforms.
"""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
import sys
import time
from typing import Any

IS_WIN = sys.platform == "win32"

# Windows has no SIGKILL; ``kill_process_group`` force-kills the whole tree there whatever signal it is given.
# Every caller names the signal through this constant: ``signal.SIGKILL`` raises AttributeError on Windows,
# at import time when it is a default argument.
SIGKILL: signal.Signals = signal.SIGTERM if sys.platform == "win32" else signal.SIGKILL


def get_process_group_kwargs() -> dict[str, Any]:
    """Return kwargs for subprocess.Popen / asyncio.create_subprocess_exec.

    ``Any`` is intentional: the resulting dict is unpacked into stdlib APIs
    whose parameter types are platform-specific (``creationflags`` on Win,
    ``start_new_session`` on POSIX) and otherwise refused by ``mypy`` when
    fed through ``**kwargs``.
    """
    if IS_WIN:
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 512)
        return {"creationflags": creationflags}
    return {"start_new_session": True}


def kill_process_group(pid: int, sig: int = SIGKILL) -> None:
    """Kill an entire process tree/group across platforms."""
    if IS_WIN:
        # On Windows, taskkill /T /F is the most reliable way to kill a process tree
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True, check=False)
    else:
        try:
            pgid = os.getpgid(pid)
            if pgid == os.getpgid(os.getpid()):
                # Safety check: do not kill our own process group!
                os.kill(pid, sig)
            else:
                os.killpg(pgid, sig)
        except (ProcessLookupError, OSError):
            pass


def kill_spawned_group(pid: int, sig: int = SIGKILL) -> None:
    """Kill the process group that ``get_process_group_kwargs()`` made for the child with this pid.

    ``kill_process_group`` finds the group through the child's pid, which stops working once the child has exited and
    been reaped while something it started keeps running. The group is named after its leader, so it is addressed by
    that pid directly, and it exists until its last member exits. Windows has no group named after a pid: there the
    tree is killed from the pid, which needs the child itself to still exist.

    The pid must be one this code started with ``get_process_group_kwargs()``: it is used as the group id as it is.
    While a member of the group runs, POSIX keeps that id from going to another process; once the last member has
    exited, a new group leader can take it, and a signal sent then reaches that unrelated group. Call this when the
    stop is due, not later.
    """
    if IS_WIN:
        kill_process_group(pid, sig)
        return
    if pid <= 1:
        # killpg(0) would signal this process's own group, and group 1 belongs to init.
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, sig)


def _is_process_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return False
    return True


def terminate_process_graceful(pid: int, *, grace_seconds: float = 2.0) -> None:
    """Send SIGTERM to a process tree, wait, then SIGKILL survivors."""
    kill_process_group(pid, signal.SIGTERM)
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline:
        if not _is_process_alive(pid):
            return
        time.sleep(0.05)
    kill_process_group(pid, SIGKILL)
