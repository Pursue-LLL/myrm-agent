"""Wall-clock budgets of the E2E waits, scaled by the load of parallel runs.

[INPUT]
- dev_gate.contract::E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV, SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC (POS: Dev Gate contract SSOT: error tokens, parallel caps and timeout budgets)
- dev_gate.contract.parallel_pressure::wave_active_lease_count_for_mux (POS: Live pressure readings that scale budgets under parallel runs: wave leases, live sessions and signoff peers)
- mux.transport_supervisor::bootstrap_wall_cap_sec, parallel_active_test_count, parallel_mux_peer_count (POS: Dev Gate transport layer: recovery mutex, per-session recover budget, bootstrap wall caps)

[OUTPUT]
- shpoib_parallel_shell_timeout_sec, shpoib_shell_wait_slice_cap: shell hydration budget and per-iteration wait cap of parallel SHPOIB runs
- signoff_parallel_force_chat_timeout_sec: force-chat wall budget under parallel signoff load
- signoff_parallel_desktop_*_sec, _signoff_desktop_soak_parallel_load: desktop signoff wall-clock, progress API, approval, mux step and turn-done budgets
- e2e_attach_timeout_ms, e2e_private_api_ready_timeout_sec, e2e_parallel_config_api_timeout_sec: attach, private API ready and config API budgets

[POS]
Turns a base timeout into the budget a parallel run needs, from the active wave leases, parallel tests and mux peers.
"""

from __future__ import annotations

import os

from dev_gate.contract import parallel_pressure


def _parallel_probe_load(*, mux_peers: bool = True) -> int:
    """Highest of the wave-lease, parallel-test and (optionally) mux-peer readings; a reading that fails counts 0."""
    leases = parallel_pressure.wave_active_lease_count_for_mux()
    try:
        from mux.transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        tests = parallel_active_test_count()
        peers = parallel_mux_peer_count() if mux_peers else 0
    except (ImportError, OSError, RuntimeError):
        tests = peers = 0
    return max(leases, tests, peers)


def shpoib_parallel_shell_timeout_sec(timeout_sec: float) -> float:
    """Shell hydration budget for parallel SHPOIB chrome_e2e on shared UI.

    cap at bootstrap wall — never 420s outer deadline that
    defeats SHELL_PROBE_STALL_FAIL_FAST_SEC skeleton fail-fast.
    signoff parallel uses pessimistic bootstrap cap (not 180s mux-undercount).
    """
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return timeout_sec
    signoff = os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    active_leases = parallel_pressure.wave_active_lease_count_for_mux()
    pessimistic = signoff and active_leases >= 2
    try:
        from mux.transport_supervisor import bootstrap_wall_cap_sec

        bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=pessimistic))
    except ImportError:
        from dev_gate.contract import E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV

        bootstrap_cap = float(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV)
    base_floor = max(timeout_sec, 120.0)
    scaled = max(base_floor, 120.0 + active_leases * 15.0)
    return min(scaled, bootstrap_cap)


def signoff_parallel_force_chat_timeout_sec(base_sec: float) -> float:
    """Extend desktop signoff force-chat wall timeouts under parallel wave load."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    load = _parallel_probe_load()
    # Signoff always applies a parallel headroom floor (Run#11 showed 50s/35s base under load).
    floor = max(base_sec, 90.0 if base_sec >= 45.0 else 70.0)
    scaled = floor + load * 12.0
    cap = 420.0
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        try:
            from dev_gate.contract import SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC

            cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC)
        except ImportError:
            cap = 420.0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in ("1", "true", "yes"):
        # desktop leg soak — force chat shell hydrate under parallel mux/turbopack.
        scaled = floor + load * 22.0 + 120.0
        cap = max(cap, 780.0)
    return min(scaled, cap)


def e2e_attach_timeout_ms(base_ms: int = 60_000) -> int:
    """Scale attachToChat poll deadline under parallel chrome_e2e load."""
    load = _parallel_probe_load()
    if load <= 1:
        return base_ms
    scaled = base_ms + load * 15_000
    return min(int(scaled), 180_000)


def e2e_private_api_ready_timeout_sec(base_sec: float = 60.0) -> float:
    """Poll budget for epoch-pinned private pool API before page binding (parallel SHPOIB)."""
    load = _parallel_probe_load(mux_peers=False)
    scaled = max(base_sec, 60.0 + load * 25.0)
    return min(scaled, 180.0)


def e2e_parallel_config_api_timeout_sec(base_sec: float) -> float:
    """Scale omni-config API timeouts under parallel chrome_e2e load (Phase C ramp SSOT)."""
    load = _parallel_probe_load(mux_peers=False)
    if load <= 0:
        return base_sec
    floor = max(base_sec, 15.0)
    scaled = floor + load * 10.0
    return min(scaled, 120.0)


def signoff_parallel_desktop_wall_clock_fail_sec(base_sec: float = 280.0) -> float:
    """Extend desktop approval per-attempt wall under parallel desktop soak."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() not in ("1", "true", "yes"):
        return base_sec
    load = _parallel_probe_load()
    floor = max(base_sec, 280.0)
    scaled = floor + load * 35.0
    return min(scaled, 600.0)


def signoff_parallel_desktop_progress_api_wall_sec(base_sec: float = 15.0) -> float:
    """Extend desktop progress API poll wall under parallel desktop soak."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() not in ("1", "true", "yes"):
        return base_sec
    load = _parallel_probe_load()
    # solo signoff desktop soak still needs >15s under mux/API load (v5 hit 15s wall).
    floor = max(base_sec, 45.0)
    scaled = floor + load * 4.0
    return min(scaled, 120.0)


def _signoff_desktop_soak_parallel_load() -> int:
    """Shared parallel-pressure load for desktop soak timeout scaling."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return 0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() not in ("1", "true", "yes"):
        return 0
    return _parallel_probe_load()


def signoff_parallel_desktop_approval_wait_sec(base_sec: float = 240.0) -> float:
    """Extend desktop tool-activity wait under parallel desktop soak."""
    load = _signoff_desktop_soak_parallel_load()
    if load <= 0:
        return base_sec
    floor = max(base_sec, 240.0)
    scaled = floor + load * 35.0
    return min(scaled, 600.0)


def signoff_parallel_desktop_mux_step_timeout_sec(base_sec: float = 75.0) -> float:
    """Extend mux-bound desktop steps (click_new_chat, ensure_surface) under soak."""
    load = _signoff_desktop_soak_parallel_load()
    if load <= 0:
        return base_sec
    floor = max(base_sec, 75.0)
    scaled = floor + load * 12.0
    return min(scaled, 240.0)


def signoff_parallel_desktop_turn_done_timeout_sec(base_sec: float = 180.0) -> float:
    """Extend post-approval DONE wait under parallel desktop soak."""
    load = _signoff_desktop_soak_parallel_load()
    if load <= 0:
        return base_sec
    floor = max(base_sec, 180.0)
    scaled = floor + load * 30.0
    return min(scaled, 420.0)


def shpoib_shell_wait_slice_cap(remaining_sec: float) -> float:
    """Per-iteration cap for MCP shell wait loops (parallel SHPOIB needs >60s)."""
    remaining_sec = max(0.0, remaining_sec)
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1":
        return max(60.0, min(remaining_sec, 180.0))
    return min(remaining_sec, 60.0)
