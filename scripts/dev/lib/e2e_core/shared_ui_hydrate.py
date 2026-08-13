"""Serialize shared :3000 UI navigate/reload bursts for parallel SHPOIB Chrome E2E.

R36: the flock guards **navigate/reload bursts** only — not MCP probe polling loops.
Holding the lock during long probe loops caused 180s×retry silent blocking (BUG-022).
"""

from __future__ import annotations

import asyncio
import contextvars
import fcntl
import os
import sys
import time
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path
from typing import AsyncIterator, Iterator
from e2e_core.real_user_home import real_user_home

DEFAULT_POLL_SEC = 2


def _default_shared_ui_hydrate_wait_sec() -> int:
    from dev_gate.contract import shared_ui_hydrate_wait_sec

    return shared_ui_hydrate_wait_sec()


# R68: nested navigate/reload bursts on one asyncio task must not re-enter flock.
_burst_depth_var: contextvars.ContextVar[int] = contextvars.ContextVar(
    "e2e_shared_ui_burst_depth", default=0
)


def _state_dir() -> Path:
    raw = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if raw:
        return Path(raw)
    return real_user_home() / ".local/state/myrm-dev"


def _lock_path() -> Path:
    return _state_dir() / "shared-ui-hydrate.lock"


def _bound_runtime_cell_id() -> str:
    """Return a cell binding only when its metadata still exists.

    A released cell environment can survive in an in-process test runner or a
    reused subprocess.  Treating that stale value as authoritative silently
    diverts the SHARED hydrate burst to a non-existent per-cell lock.
    """
    cell_id = os.environ.get("MYRM_E2E_CELL_ID", "").strip()
    if not cell_id:
        return ""
    try:
        from e2e_core.runtime_cell import cell_hydrate_lock_path

        if cell_hydrate_lock_path(cell_id).parent.joinpath("cell-meta.json").is_file():
            return cell_id
    except (ImportError, OSError, RuntimeError):
        return ""
    return ""


def _monorepo_root() -> Path | None:
    override = os.environ.get("MYRM_MONOREPO_ROOT", "").strip()
    if override:
        return Path(override)
    agent_root = os.environ.get("MYRM_AGENT_ROOT", "").strip()
    if agent_root:
        return Path(agent_root).parent
    return None


def shpoib_shared_ui_queue_enabled() -> bool:
    return os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1"


def parallel_shared_ui_hydrate_queue_enabled() -> bool:
    """Serialize shared :3000 compile bursts for parallel Chrome E2E (SHPOIB + READ shared-hot)."""
    if os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1":
        return False
    if shpoib_shared_ui_queue_enabled():
        return True
    if os.environ.get("MYRM_PRIVATE_BACKEND", "").strip() == "1":
        return False
    try:
        from dev_gate.contract import phase_c_burst_lane_count

        if phase_c_burst_lane_count() >= 2:
            return True
    except ImportError:
        pass
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        try:
            from mux.transport_supervisor import parallel_active_test_count

            if parallel_active_test_count() >= 2:
                return True
        except ImportError:
            pass
    root = _monorepo_root()
    if root is None:
        return False
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        return wave_active_lease_count(root) > 1
    except (ImportError, OSError, RuntimeError, ValueError):
        return False


@contextmanager
def shared_ui_hydrate_slot() -> Iterator[None]:
    """Exclusive slot for shared UI shell hydration (SHPOIB parallel only)."""
    if not parallel_shared_ui_hydrate_queue_enabled():
        yield
        return

    cell_id = _bound_runtime_cell_id()
    if cell_id:
        from e2e_core.runtime_cell import cell_ui_hydrate_slot

        wait_sec = int(
            os.environ.get(
                "MYRM_E2E_SHARED_UI_HYDRATE_WAIT_SEC",
                str(_default_shared_ui_hydrate_wait_sec()),
            )
        )
        with cell_ui_hydrate_slot(wait_sec=wait_sec):
            yield
        return

    wait_sec = int(
        os.environ.get(
            "MYRM_E2E_SHARED_UI_HYDRATE_WAIT_SEC",
            str(_default_shared_ui_hydrate_wait_sec()),
        )
    )
    poll_sec = max(
        1,
        int(
            os.environ.get("MYRM_E2E_SHARED_UI_HYDRATE_POLL_SEC", str(DEFAULT_POLL_SEC))
        ),
    )
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
    if not parallel_shared_ui_hydrate_queue_enabled():
        yield
        return
    depth = _burst_depth_var.get()
    if depth > 0:
        token = _burst_depth_var.set(depth + 1)
        try:
            yield
        finally:
            _burst_depth_var.reset(token)
        return
    token = _burst_depth_var.set(1)
    try:
        with shared_ui_hydrate_slot():
            yield
    finally:
        _burst_depth_var.reset(token)


@asynccontextmanager
async def async_shared_ui_hydrate_burst() -> AsyncIterator[None]:
    """Async navigate/reload burst slot (R36)."""
    if not parallel_shared_ui_hydrate_queue_enabled():
        yield
        return
    depth = _burst_depth_var.get()
    if depth > 0:
        token = _burst_depth_var.set(depth + 1)
        try:
            yield
        finally:
            _burst_depth_var.reset(token)
        return
    token = _burst_depth_var.set(1)
    try:
        slot = shared_ui_hydrate_slot()
        await asyncio.to_thread(slot.__enter__)
        try:
            yield
        finally:
            await asyncio.to_thread(slot.__exit__, None, None, None)
    finally:
        _burst_depth_var.reset(token)


@asynccontextmanager
async def async_shared_ui_hydrate_slot() -> AsyncIterator[None]:
    """Async wrapper for ``shared_ui_hydrate_slot`` (SHPOIB parallel Chrome E2E)."""
    if not parallel_shared_ui_hydrate_queue_enabled():
        yield
        return
    slot = shared_ui_hydrate_slot()
    await asyncio.to_thread(slot.__enter__)
    try:
        yield
    finally:
        await asyncio.to_thread(slot.__exit__, None, None, None)
