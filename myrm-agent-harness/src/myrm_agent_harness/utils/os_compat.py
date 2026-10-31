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
- LOCK_EX, LOCK_SH, LOCK_NB, LOCK_UN: Cross-platform lock flags.
- flock: Cross-platform fcntl.flock wrapper.
- lockf: Cross-platform fcntl.lockf wrapper.

[POS]
Provides unified abstractions for POSIX/Windows differences (file locks, process groups)
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

if IS_WIN:
    # msvcrt is a Windows-only stdlib; mypy on POSIX cannot see its members.
    import msvcrt  # type: ignore[import-not-found,unused-ignore,reportMissingImports]

    LOCK_EX = 1  # Dummy mapping
    LOCK_SH = 2
    LOCK_NB = 4
    LOCK_UN = 8

    def _win_lock(fd_or_file: Any, op: int, length: int = 1) -> None:
        fd = fd_or_file if isinstance(fd_or_file, int) else fd_or_file.fileno()
        # msvcrt.locking requires locking the current position, so we save it, seek to 0, lock, then restore
        pos = os.lseek(fd, 0, os.SEEK_CUR)
        os.lseek(fd, 0, os.SEEK_SET)

        mode = msvcrt.LK_NBLCK if (op & LOCK_NB) else msvcrt.LK_LOCK  # type: ignore[attr-defined]
        if op & LOCK_UN:
            mode = msvcrt.LK_UNLCK  # type: ignore[attr-defined]

        try:
            msvcrt.locking(fd, mode, length)  # type: ignore[attr-defined]
        except OSError as e:
            if op & LOCK_NB:
                raise BlockingIOError() from e
            raise
        finally:
            os.lseek(fd, pos, os.SEEK_SET)

    def flock(fd: Any, op: int) -> None:
        _win_lock(fd, op, 1)

    def lockf(fd: Any, op: int, length: int = 0, start: int = 0, whence: int = 0) -> None:
        # length=0 means whole file in fcntl. On Windows we lock a large number of bytes.
        # But we mostly only need 1 byte lock to coordinate inter-process for same-file locks.
        _win_lock(fd, op, length if length > 0 else 1)
else:
    import fcntl

    LOCK_EX = fcntl.LOCK_EX
    LOCK_SH = fcntl.LOCK_SH
    LOCK_NB = fcntl.LOCK_NB
    LOCK_UN = fcntl.LOCK_UN

    def flock(fd: Any, op: int) -> None:
        fcntl.flock(fd, op)

    def lockf(fd: Any, op: int, length: int = 0, start: int = 0, whence: int = 0) -> None:
        fcntl.lockf(fd, op, length, start, whence)


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
