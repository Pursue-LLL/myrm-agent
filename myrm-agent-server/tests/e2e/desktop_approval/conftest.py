"""Pytest hooks for desktop approval Chrome E2E (single-flight guard).

[INPUT]
- fcntl / os / time (stdlib session lock)

[OUTPUT]
- _desktop_approval_e2e_single_flight: session autouse fixture

[POS]
Desktop approval E2E package guard; queues duplicate pytest sessions instead of failing.
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

_LOCK_PATH = Path(os.environ.get("TMPDIR", "/tmp")) / "myrm-desktop-approval-e2e.lock"
_LOCK_WAIT_SEC = float(os.environ.get("MYRM_DESKTOP_E2E_LOCK_WAIT_SEC", "900"))


@pytest.fixture(scope="session", autouse=True)
def _desktop_approval_e2e_single_flight() -> Iterator[None]:
    """Queue duplicate desktop approval pytest sessions (FIFO via blocking flock)."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    deadline = time.monotonic() + _LOCK_WAIT_SEC
    acquired = False
    last_log = 0.0
    while time.monotonic() < deadline:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            acquired = True
            break
        except BlockingIOError:
            now = time.monotonic()
            if now - last_log >= 30.0:
                print(
                    f"DESKTOP_E2E_LOCK_WAIT: another desktop approval session holds "
                    f"{_LOCK_PATH}; queueing (max {_LOCK_WAIT_SEC:.0f}s)",
                    flush=True,
                )
                last_log = now
            time.sleep(1.0)
    if not acquired:
        os.close(fd)
        pytest.fail(
            "Timed out waiting for desktop approval Chrome E2E lock "
            f"(lock={_LOCK_PATH}, wait={_LOCK_WAIT_SEC:.0f}s). "
            "Another desktop pytest is still running — do not start a duplicate; wait for queue."
        )
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
