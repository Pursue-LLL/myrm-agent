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


def owner_process_matches(*, pid: int, expected_start: str) -> bool:
    """True when pid is alive and still the same OS process instance."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    if not expected_start.strip():
        return True
    from process_identity import capture_process

    current = capture_process(pid, role="e2e-owner", runtime_id="owner")
    if current is None:
        # Distinguish zombie (dead for reap) from transient ps parse failure.
        try:
            result = subprocess.run(
                ["ps", "-p", str(pid), "-o", "stat="],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            return True
        if result.returncode != 0:
            return False
        if "Z" in result.stdout:
            return False
        return True
    return current["startedAt"] == expected_start
