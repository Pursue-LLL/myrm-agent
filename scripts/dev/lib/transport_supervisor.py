"""TransportSupervisor — mux runtime invariants for parallel Chrome E2E (R65-A).

[INPUT]
- runtime_probe.mux_owned_daemon_count
- dev_gate_contract.MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC

[OUTPUT]
- assert_mux_daemons_single(), mux_recovery_scope(), recovery_budget_remaining()

[POS]
Dev Gate transport layer — global recovery mutex, per-session cumulative recover
budget, runtime muxDaemons==1 fail-closed before new_page/recover.

P0-B: mux cold-attach / new_page must acquire operation credits via
browser_orchestrator.browser_operation_credit_slot (enforced by static tests).
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
    MUX_UPSTREAM_WAIT_SEC,
)

MUX_SESSION_RECOVERY_BUDGET_SEC: float = 120.0
MUX_SESSION_RECOVERY_BUDGET_MAX_SEC: float = 300.0
MUX_SESSION_RECOVERY_BUDGET_PER_PEER_SEC: float = 30.0
MUX_UPSTREAM_WAIT_BASE_SEC: float = float(MUX_UPSTREAM_WAIT_SEC)
MUX_UPSTREAM_WAIT_MAX_SEC: float = 600.0
MUX_UPSTREAM_WAIT_PER_PEER_SEC: float = 45.0
MUX_BOOTSTRAP_WALL_BASE_SEC: float = 180.0
MUX_BOOTSTRAP_WALL_MAX_SEC: float = 420.0
MUX_BOOTSTRAP_WALL_PER_PEER_SEC: float = 45.0
LIVE_AGENT_BODY_WALL_BASE_SEC: float = 600.0
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


def _mux_peer_count(*, pessimistic: bool = False) -> int:
    """Peer load for cap scaling; pessimistic floor for pytest-timeout under signoff waves (R108)."""
    peers = parallel_mux_peer_count()
    if not pessimistic:
        return peers
    from dev_gate_contract import (  # noqa: PLC0415
        DEFAULT_BOOTSTRAP_SLOTS,
        SHARED_BROWSER_WORKERS,
    )

    floor = SHARED_BROWSER_WORKERS + DEFAULT_BOOTSTRAP_SLOTS + 1
    return max(peers, floor)


def session_recovery_budget_cap(*, pessimistic: bool = False) -> float:
    """Scale mux recovery budget under parallel wave/mux peers (R100)."""
    peers = _mux_peer_count(pessimistic=pessimistic)
    if peers <= 3:
        scaled = MUX_SESSION_RECOVERY_BUDGET_SEC
    else:
        scaled = MUX_SESSION_RECOVERY_BUDGET_SEC + (
            (peers - 3) * MUX_SESSION_RECOVERY_BUDGET_PER_PEER_SEC
        )
    cap = min(MUX_SESSION_RECOVERY_BUDGET_MAX_SEC, scaled)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1" and os.environ.get(
        "MYRM_E2E_DESKTOP_SOAK", ""
    ).strip() in ("1", "true", "yes"):
        # Desktop leg soak runs under parallel chrome_e2e; force-chat-shell recover
        # can consume the default 120–300s budget before approval BODY starts.
        cap = min(MUX_SESSION_RECOVERY_BUDGET_MAX_SEC + 180.0, cap + 180.0)
    return cap


def mux_upstream_wait_cap(*, pessimistic: bool = False) -> int:
    """Scale mux cold-attach queue wait under parallel wave/mux peers (R101)."""
    peers = _mux_peer_count(pessimistic=pessimistic)
    if peers <= 3:
        return int(MUX_UPSTREAM_WAIT_BASE_SEC)
    scaled = MUX_UPSTREAM_WAIT_BASE_SEC + ((peers - 3) * MUX_UPSTREAM_WAIT_PER_PEER_SEC)
    cap = min(MUX_UPSTREAM_WAIT_MAX_SEC, scaled)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1" and os.environ.get(
        "MYRM_E2E_DESKTOP_SOAK", ""
    ).strip() in ("1", "true", "yes"):
        cap = min(MUX_UPSTREAM_WAIT_MAX_SEC + 120.0, cap + 120.0)
    return int(cap)


def bootstrap_wall_cap_sec(*, pessimistic: bool = False) -> int:
    """Scale SHPOIB bootstrap wall under parallel wave/mux peers (R102)."""
    peers = _mux_peer_count(pessimistic=pessimistic)
    if peers <= 3:
        return int(MUX_BOOTSTRAP_WALL_BASE_SEC)
    scaled = MUX_BOOTSTRAP_WALL_BASE_SEC + (
        (peers - 3) * MUX_BOOTSTRAP_WALL_PER_PEER_SEC
    )
    return int(min(MUX_BOOTSTRAP_WALL_MAX_SEC, scaled))


def live_agent_body_wall_cap_sec(*, pessimistic: bool = False) -> int:
    """Return the invariant LIVE_AGENT BODY hard wall."""
    del pessimistic
    return int(LIVE_AGENT_BODY_WALL_BASE_SEC)


def live_agent_pytest_wall_cap_sec(*, pessimistic_peers: bool = False) -> int:
    """pytest-timeout outer cap: bootstrap + body + teardown + mux queue + recovery (R103/R105/R108)."""
    from dev_gate_contract import E2E_TEARDOWN_WALL_CLOCK_SEC  # noqa: PLC0415

    return (
        bootstrap_wall_cap_sec(pessimistic=pessimistic_peers)
        + live_agent_body_wall_cap_sec(pessimistic=pessimistic_peers)
        + E2E_TEARDOWN_WALL_CLOCK_SEC
        + mux_upstream_wait_cap(pessimistic=pessimistic_peers)
        + int(session_recovery_budget_cap(pessimistic=pessimistic_peers))
    )


def _signoff_recovery_budget_pessimistic() -> bool:
    return os.environ.get("E2E_SIGNOFF", "").strip() == "1"


def recovery_budget_remaining() -> float:
    key = session_key()
    cap = session_recovery_budget_cap(
        pessimistic=_signoff_recovery_budget_pessimistic()
    )
    with _session_lock:
        spent = _session_recovery_spent.get(key, 0.0)
    return max(0.0, cap - spent)


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
    policy_wave_leases = 0
    try:
        from pathlib import Path

        from stack_mutation_policy import wave_active_lease_count

        policy_wave_leases = max(
            0, wave_active_lease_count(Path(__file__).resolve().parents[4])
        )
    except ImportError:
        pass
    return max(
        wave_leases,
        mux_contexts,
        daemon_count,
        parallel_active_test_count(),
        policy_wave_leases,
    )


def recovery_lock_wait_sec() -> float:
    active = parallel_mux_peer_count()
    scaled = MUX_RECOVERY_LOCK_BASE_SEC + active * MUX_RECOVERY_LOCK_PER_ACTIVE_SEC
    cap = MUX_RECOVERY_LOCK_WAIT_SEC
    try:
        from dev_gate_contract import (  # noqa: PLC0415
            _parallel_signoff_pressure_peers,
            is_e2e_signoff_runtime,
        )

        if is_e2e_signoff_runtime():
            pressure = max(active, _parallel_signoff_pressure_peers())
            scaled = MUX_RECOVERY_LOCK_BASE_SEC + pressure * 35.0
            cap = 300.0  # R229/R230: v155-v156 post-SEND_TURN attach under mux_peers≥7
    except ImportError:
        pass
    return min(cap, scaled)


def assert_mux_daemons_single(*, phase: str) -> None:
    from runtime_probe import mux_owned_daemon_count  # noqa: PLC0415

    count = mux_owned_daemon_count()
    if count == 0 and phase in (
        "restart_cold_shim",
        "force_mux_attach_restart",
        "new_page",
        "recover_mux_transport",
    ):
        # R190/R213: parallel abandon may teardown all mux daemons — recover paths respawn.
        return
    if count != 1:
        raise RuntimeError(
            f"{MUX_DAEMONS_FAIL_CLOSED_TOKEN}: muxDaemons={count} expected=1 "
            f"phase={phase}"
        )


def _reserve_recovery_budget(*, phase: str) -> float:
    remaining = recovery_budget_remaining()
    if remaining <= 0.0:
        cap = session_recovery_budget_cap(
            pessimistic=_signoff_recovery_budget_pessimistic()
        )
        raise RuntimeError(
            f"{MUX_TRANSPORT_EXHAUSTED_TOKEN}: session recovery budget "
            f"{int(cap)}s exhausted at phase={phase}"
        )
    reclaim_cap = float(MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC)
    if _signoff_recovery_budget_pessimistic():
        from dev_gate_contract import mux_page_reclaim_hard_timeout_sec  # noqa: PLC0415

        reclaim_cap = float(mux_page_reclaim_hard_timeout_sec())
    return min(remaining, reclaim_cap)


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
