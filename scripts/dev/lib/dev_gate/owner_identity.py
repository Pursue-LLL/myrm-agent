"""Owner identity helpers for Dev Gate coordinator sessions (P0-A)."""

from __future__ import annotations

import os
import platform
import subprocess
import time
from pathlib import Path


def read_boot_session_id() -> str:
    """Return a stable boot-session marker for PID reuse detection."""
    system = platform.system()
    if system == "Darwin":
        try:
            result = subprocess.run(
                ["sysctl", "-n", "kern.boottime"],
                capture_output=True,
                text=True,
                check=True,
            )
            boot_marker = result.stdout.strip()
            if boot_marker:
                return f"darwin:{boot_marker}"
        except OSError:
            pass
    if system == "Linux":
        try:
            first_line = Path("/proc/stat").read_text(encoding="utf-8").splitlines()[0]
            if first_line.startswith("btime "):
                return f"linux:{first_line.split()[1]}"
        except OSError:
            pass
    return f"fallback-day:{int(time.time()) // 86400}"


def capture_owner_process_start(pid: int) -> str:
    """Capture ps lstart token for the owning process."""
    if pid <= 0:
        return ""
    from process_identity import capture_process

    identity = capture_process(pid, role="e2e-owner", runtime_id="owner")
    if identity is None:
        return ""
    return identity["startedAt"]


def _start_epoch_sec(token: str) -> float | None:
    """Normalize a startedAt token to epoch seconds.

    ``startedAt`` appears in two shapes depending on which identity backend
    captured it: ``ps -o lstart`` (``Wed Aug 12 15:54:32 2026``, local time)
    or the psutil fallback (``unix:<create_time>``, already epoch). Comparing
    the raw strings fails whenever submit and reap hit different backends
    (e.g. ``ps`` briefly denied under host load), misreading a live owner as
    exited and reaping a healthy session. Normalize both to epoch seconds.
    """
    token = token.strip()
    if not token:
        return None
    if token.startswith("unix:"):
        try:
            value = float(token[len("unix:") :])
        except ValueError:
            return None
        if value != value:  # nan guard (float("nan") parses without raising)
            return None
        return value
    try:
        return time.mktime(time.strptime(token, "%a %b %d %H:%M:%S %Y"))
    except (ValueError, OverflowError):
        return None


def owner_process_matches(*, pid: int, expected_start: str) -> bool:
    """True when pid is alive and still the same OS process instance."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    except OSError:
        return False
    if not expected_start.strip():
        return True
    from process_identity import capture_process

    current = capture_process(pid, role="e2e-owner", runtime_id="owner")
    if current is None:
        # A missing identity is not proof of ownership.  In particular, a
        # sandbox may deny spawning `ps`; treating that uncertainty as a match
        # would let deadline cleanup signal the coordinator or a peer process.
        # Keep the reaper fail-closed until PID + start token are observable.
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "stat="],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return False
        if result.returncode != 0:
            return False
        if "Z" in result.stdout:
            return False
        return True
    expected_epoch = _start_epoch_sec(expected_start)
    current_epoch = _start_epoch_sec(current["startedAt"])
    if expected_epoch is None or current_epoch is None:
        # Unparseable tokens (never observed in practice) keep the strict
        # string equality as a fail-closed fallback.
        return current["startedAt"] == expected_start
    # Cross-backend normalization may differ by sub-second rounding; a 2s
    # window is far tighter than any real PID-reuse gap.
    return abs(current_epoch - expected_epoch) <= 2.0
