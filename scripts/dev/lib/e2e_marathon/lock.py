"""Marathon exclusive lock — blocks parallel chrome_e2e submit."""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _read_lock(lock_file: Path) -> dict[str, Any] | None:
    if not lock_file.is_file():
        return None
    try:
        payload = json.loads(lock_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def acquire_lock(lock_file: Path, worker_pid: int, worker_token: str) -> bool:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    existing = _read_lock(lock_file)
    if existing is not None:
        holder = int(existing.get("pid", 0))
        if holder != worker_pid and _pid_alive(holder):
            return False
    payload = {
        "pid": worker_pid,
        "token": worker_token,
        "acquired_at": time.time(),
    }
    lock_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return True


def release_lock(lock_file: Path, worker_pid: int) -> None:
    existing = _read_lock(lock_file)
    if existing is None:
        return
    holder = int(existing.get("pid", 0))
    if holder == worker_pid:
        lock_file.unlink(missing_ok=True)


def _process_descendant_of(pid: int, ancestor: int, depth: int = 12) -> bool:
    if pid <= 0 or ancestor <= 0:
        return False
    if pid == ancestor:
        return True
    if depth <= 0:
        return False
    try:
        out = subprocess.run(
            ["ps", "-o", "ppid=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
        ppid = int(out.stdout.strip())
    except (OSError, ValueError):
        return False
    if ppid <= 0 or ppid == pid:
        return False
    return _process_descendant_of(ppid, ancestor, depth - 1)


def marathon_exclusive_blocked(lock_file: Path, submitter_pid: int) -> str | None:
    """Return error message when submit must be rejected."""
    existing = _read_lock(lock_file)
    if existing is None:
        return None
    holder = int(existing.get("pid", 0))
    if holder <= 0 or not _pid_alive(holder):
        return None
    if holder == submitter_pid or _process_descendant_of(submitter_pid, holder):
        return None
    token = os.environ.get("MYRM_MARATHON_WORKER_TOKEN", "").strip()
    lock_token = str(existing.get("token", "")).strip()
    if token and lock_token and token == lock_token:
        return None
    return (
        f"E2E_MARATHON_EXCLUSIVE: marathon supervisor pid={holder} holds exclusive "
        f"chrome_e2e admission; submitter pid={submitter_pid} rejected"
    )
