"""Pytest hooks for desktop approval Chrome E2E (single-flight guard).

[INPUT]
- fcntl / os (stdlib session lock)

[OUTPUT]
- _desktop_approval_e2e_single_flight: session autouse fixture

[POS]
Desktop approval E2E package guard; prevents duplicate pytest sessions from mux contention.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Iterator
from pathlib import Path

import pytest

_LOCK_PATH = Path(os.environ.get("TMPDIR", "/tmp")) / "myrm-desktop-approval-e2e.lock"


@pytest.fixture(scope="session", autouse=True)
def _desktop_approval_e2e_single_flight() -> Iterator[None]:
    """Prevent duplicate desktop approval pytest sessions from contending on mux."""
    _LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(_LOCK_PATH, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        pytest.fail(
            "Another desktop approval Chrome E2E session is already running "
            f"(lock={_LOCK_PATH}). Wait for it to finish instead of starting a duplicate."
        )
    try:
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
