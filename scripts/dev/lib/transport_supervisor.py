"""TransportSupervisor — mux runtime invariants for parallel Chrome E2E (R65-A).

[INPUT]
- runtime_probe.mux_owned_daemon_count
- dev_gate_contract.MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC

[OUTPUT]
- assert_mux_daemons_single(), mux_recovery_scope(), recovery_budget_remaining()

[POS]
Dev Gate transport layer — global recovery mutex, per-session cumulative recover
budget, runtime muxDaemons==1 fail-closed before new_page/recover.
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from typing import Iterator

from dev_gate_contract import (
    MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC,
    MUX_RECLAIM_STALL_TOKEN,
)

MUX_SESSION_RECOVERY_BUDGET_SEC: float = 120.0
MUX_RECOVERY_LOCK_WAIT_SEC: float = 90.0
MUX_RECOVERY_LOCK_BASE_SEC: float = 15.0
MUX_RECOVERY_LOCK_PER_ACTIVE_SEC: float = 20.0
MUX_TRANSPORT_EXHAUSTED_TOKEN: str = "E2E_MUX_TRANSPORT_EXHAUSTED"
MUX_DAEMONS_FAIL_CLOSED_TOKEN: str = "E2E_MUX_DAEMONS_FAIL_CLOSED"

_GLOBAL_RECOVERY_LOCK = threading.Lock()
_session_recovery_spent: dict[str, float] = {}
_session_lock = threading.Lock()


def session_key() -> str:
    cell_id = os.environ.get("MYRM_E2E_CELL_ID", "").strip()
    if cell_id:
        return cell_id
    for name in ("MYRM_E2E_RUN_ID", "MYRM_E2E_AGENT_ID", "MYRM_WAVE_AGENT_ID"):
        raw = os.environ.get(name, "").strip()
        if raw:
            return raw
    return f"pid-{os.getpid()}"


def recovery_budget_remaining() -> float:
    key = session_key()
    with _session_lock:
        spent = _session_recovery_spent.get(key, 0.0)
    return max(0.0, MUX_SESSION_RECOVERY_BUDGET_SEC - spent)


def parallel_active_test_count() -> int:
    """Best-effort parallel chrome_e2e count for recovery mutex scaling (R73-F TPC M3)."""
    raw = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_COUNT", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    try:
        from e2e_runtime_cell import count_live_runtime_cells

        return max(1, count_live_runtime_cells())
    except ImportError:
        pass
    return 1


def parallel_mux_peer_count() -> int:
    """Wave/mux peer load for recovery lock scaling (align with chrome_mcp_client TRSM)."""
    wave_leases = 0
    mux_contexts = 0
    try:
        from mux_load import snapshot_mux_load

        snapshot = snapshot_mux_load(force=True)
        wave_leases = max(0, snapshot.wave_leases)
        mux_contexts = max(0, snapshot.mux_contexts)
    except ImportError:
        pass
    daemon_count = 1
    try:
        from runtime_probe import mux_owned_daemon_count

        daemon_count = max(1, int(mux_owned_daemon_count()))
    except (ImportError, OSError, TypeError, ValueError):
        pass
    return max(wave_leases, mux_contexts, daemon_count, parallel_active_test_count())


def recovery_lock_wait_sec() -> float:
    active = parallel_mux_peer_count()
    scaled = MUX_RECOVERY_LOCK_BASE_SEC + active * MUX_RECOVERY_LOCK_PER_ACTIVE_SEC
    return min(MUX_RECOVERY_LOCK_WAIT_SEC, scaled)


def assert_mux_daemons_single(*, phase: str) -> None:
    from runtime_probe import mux_owned_daemon_count  # noqa: PLC0415

    count = mux_owned_daemon_count()
    if count != 1:
        raise RuntimeError(
            f"{MUX_DAEMONS_FAIL_CLOSED_TOKEN}: muxDaemons={count} expected=1 "
            f"phase={phase}"
        )


def _reserve_recovery_budget(*, phase: str) -> float:
    remaining = recovery_budget_remaining()
    if remaining <= 0.0:
        raise RuntimeError(
            f"{MUX_TRANSPORT_EXHAUSTED_TOKEN}: session recovery budget "
            f"{int(MUX_SESSION_RECOVERY_BUDGET_SEC)}s exhausted at phase={phase}"
        )
    return min(remaining, float(MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC))


def _record_recovery_elapsed(elapsed_sec: float) -> None:
    if elapsed_sec <= 0.0:
        return
    key = session_key()
    with _session_lock:
        _session_recovery_spent[key] = (
            _session_recovery_spent.get(key, 0.0) + elapsed_sec
        )


@contextmanager
def mux_recovery_scope(*, phase: str) -> Iterator[float]:
    """Serialize mux transport recovery globally; enforce session budget."""
    assert_mux_daemons_single(phase=phase)
    allowed_sec = _reserve_recovery_budget(phase=phase)
    lock_wait_sec = recovery_lock_wait_sec()
    acquired = _GLOBAL_RECOVERY_LOCK.acquire(timeout=lock_wait_sec)
    if not acquired:
        raise RuntimeError(
            f"{MUX_RECLAIM_STALL_TOKEN}: mux recovery lock timeout after "
            f"{lock_wait_sec:.0f}s active_tests={parallel_active_test_count()} "
            f"mux_peers={parallel_mux_peer_count()} "
            f"phase={phase}"
        )
    recovery_started = time.monotonic()
    try:
        yield allowed_sec
    finally:
        _record_recovery_elapsed(time.monotonic() - recovery_started)
        _GLOBAL_RECOVERY_LOCK.release()


def reset_session_recovery_budget(for_key: str | None = None) -> None:
    """Test helper: clear cumulative recovery spend for a session key."""
    key = for_key or session_key()
    with _session_lock:
        _session_recovery_spent.pop(key, None)
