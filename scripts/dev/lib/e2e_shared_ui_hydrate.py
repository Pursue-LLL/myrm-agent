"""Serialize shared :3000 UI navigate/reload bursts for parallel SHPOIB Chrome E2E.

R36: the flock guards **navigate/reload bursts** only — not MCP probe polling loops.
Holding the lock during long probe loops caused 180s×retry silent blocking (BUG-022).
"""

from __future__ import annotations

import asyncio
import fcntl
import os
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator

DEFAULT_WAIT_SEC = 900
DEFAULT_POLL_SEC = 2


def _state_dir() -> Path:
    raw = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if raw:
        return Path(raw)
    return Path.home() / ".local/state/myrm-dev"


def _lock_path() -> Path:
    return _state_dir() / "shared-ui-hydrate.lock"


def shpoib_shared_ui_queue_enabled() -> bool:
    return os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1"


@contextmanager
def shared_ui_hydrate_slot() -> Iterator[None]:
    """Exclusive slot for shared UI shell hydration (SHPOIB parallel only)."""
    if not shpoib_shared_ui_queue_enabled():
        yield
        return

    wait_sec = int(os.environ.get("MYRM_E2E_SHARED_UI_HYDRATE_WAIT_SEC", str(DEFAULT_WAIT_SEC)))
    poll_sec = max(1, int(os.environ.get("MYRM_E2E_SHARED_UI_HYDRATE_POLL_SEC", str(DEFAULT_POLL_SEC))))
    lock_path = _lock_path()
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()

    with lock_path.open("a+", encoding="utf-8") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                elapsed = int(time.monotonic() - started)
                print(
                    f"E2E_SHARED_UI_HYDRATE_LOCK_ACQUIRED: pid={os.getpid()} elapsed={elapsed}s",
                    file=sys.stderr,
                )
                break
            except BlockingIOError:
                elapsed = int(time.monotonic() - started)
                if elapsed >= wait_sec:
                    print(
                        f"E2E_SHARED_UI_HYDRATE_WAIT_TIMEOUT: waited {wait_sec}s",
                        file=sys.stderr,
                    )
                    raise TimeoutError(
                        f"E2E_SHARED_UI_HYDRATE_WAIT_TIMEOUT after {wait_sec}s"
                    ) from None
                print(
                    f"E2E_SHARED_UI_HYDRATE_WAIT: elapsed={elapsed}s/{wait_sec}s poll={poll_sec}s",
                    file=sys.stderr,
                )
                time.sleep(poll_sec)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def shared_ui_hydrate_burst() -> Iterator[None]:
    """Exclusive slot for navigate/reload burst only (R36 — not probe polling)."""
    with shared_ui_hydrate_slot():
        yield


@asynccontextmanager
async def async_shared_ui_hydrate_burst() -> AsyncIterator[None]:
    """Async navigate/reload burst slot (R36)."""
    if not shpoib_shared_ui_queue_enabled():
        yield
        return
    slot = shared_ui_hydrate_burst()
    await asyncio.to_thread(slot.__enter__)
    try:
        yield
    finally:
        await asyncio.to_thread(slot.__exit__, None, None, None)


@asynccontextmanager
async def async_shared_ui_hydrate_slot() -> AsyncIterator[None]:
    """Async wrapper for ``shared_ui_hydrate_slot`` (SHPOIB parallel Chrome E2E)."""
    if not shpoib_shared_ui_queue_enabled():
        yield
        return
    slot = shared_ui_hydrate_slot()
    await asyncio.to_thread(slot.__enter__)
    try:
        yield
    finally:
        await asyncio.to_thread(slot.__exit__, None, None, None)
