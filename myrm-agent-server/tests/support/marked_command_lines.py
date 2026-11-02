"""Commands that leave a marked program running, and a read-only lookup of live processes by that marker.

Used by tests that start a process through the product and then check, without signalling anything, whether it is
still there.
"""

from __future__ import annotations

import psutil


def leave_one_child_command(marker: str, *, lifetime_seconds: int) -> str:
    """A shell command that starts one child carrying ``marker`` in its command line and ends at once.

    Background jobs run on a pseudo-terminal whose hang-up reaches a child started a moment before the job ended, so
    the child ignores SIGHUP the way a daemon started with ``nohup`` does; the ignore is inherited through exec.
    """
    child = f"import time; time.sleep({lifetime_seconds})"
    return (
        'python3 -c "import signal, subprocess; signal.signal(signal.SIGHUP, signal.SIG_IGN); '
        f"subprocess.Popen(['python3', '-c', '{child}', '{marker}'], "
        'stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)"'
    )


def processes_with_marker(marker: str) -> list[int]:
    """Pids of the live (not exited-and-unreaped) processes whose command line contains ``marker``."""
    pids: list[int] = []
    for proc in psutil.process_iter(["cmdline", "status"]):
        if proc.info["status"] == psutil.STATUS_ZOMBIE:
            continue
        if any(marker in part for part in proc.info["cmdline"] or ()):
            pids.append(proc.pid)
    return pids
