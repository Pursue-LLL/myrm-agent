"""The idle-converge lock: a lock directory under /tmp that a crashed converger cannot leave behind forever.

[INPUT]
- `/tmp/plane-converge.lockdir` and its `converge.pid` (POS: one converger per host)

[OUTPUT]
- `converge_lock_dir()` / `try_acquire_converge_lock()`: acquire the lock, breaking one whose holder is dead or older than 120 s

[POS]
Dev Gate infra layer. Taken by `plane_health.converge_plane_if_idle`; the owner removes the directory when it is done.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Final

_CONVERGE_LOCK: Final[str] = "plane-converge.lockdir"


_CONVERGE_LOCK_STALE_SEC: Final[float] = 120.0


def converge_lock_dir() -> Path:
    return Path("/tmp") / _CONVERGE_LOCK


def try_acquire_converge_lock() -> bool:
    """Acquire idle converge lock; break stale lockdirs left by crashed convergers."""
    lock_dir = converge_lock_dir()
    pid_file = lock_dir / "converge.pid"
    try:
        lock_dir.mkdir(exist_ok=False)
        try:
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass
        return True
    except FileExistsError:
        # Check if the process holding the lock is dead
        is_dead = False
        try:
            if pid_file.is_file():
                raw_pid = pid_file.read_text(encoding="utf-8").strip()
                if raw_pid.isdigit():
                    pid = int(raw_pid)
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        is_dead = True
                    except (PermissionError, OSError):
                        pass
        except OSError:
            pass

        try:
            age_sec = time.time() - lock_dir.stat().st_mtime
        except OSError:
            return False
        if not is_dead and age_sec < _CONVERGE_LOCK_STALE_SEC:
            return False
        try:
            if pid_file.is_file():
                pid_file.unlink(missing_ok=True)
            lock_dir.rmdir()
        except OSError:
            return False
        try:
            lock_dir.mkdir(exist_ok=False)
            try:
                pid_file.write_text(str(os.getpid()), encoding="utf-8")
            except OSError:
                pass
            return True
        except FileExistsError:
            return False
