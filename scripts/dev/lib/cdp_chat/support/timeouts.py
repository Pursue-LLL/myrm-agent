"""Wall-clock budgets of the E2E waits, scaled by the load of parallel runs.

[INPUT]
- cdp_chat.support.paths::MONOREPO_ROOT (POS: Single source of the checkout root the E2E helpers resolve dev scripts and stack state against)
- dev_gate.contract::E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV, SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC (POS: Dev Gate contract SSOT: error tokens, parallel caps and timeout budgets)
- e2e_core.stack_mutation_policy::wave_active_lease_count (POS: shared-stack mutation decisions; defers drift heal while wave leases are active)
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

from cdp_chat.support.paths import MONOREPO_ROOT


def shpoib_parallel_shell_timeout_sec(timeout_sec: float) -> float:
    """Shell hydration budget for parallel SHPOIB chrome_e2e on shared UI.

    cap at bootstrap wall — never 420s outer deadline that
    defeats SHELL_PROBE_STALL_FAIL_FAST_SEC skeleton fail-fast.
    signoff parallel uses pessimistic bootstrap cap (not 180s mux-undercount).
    """
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return timeout_sec
    signoff = os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    active_leases = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
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
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
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
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
    if load <= 1:
        return base_ms
    scaled = base_ms + load * 15_000
    return min(int(scaled), 180_000)


def e2e_private_api_ready_timeout_sec(base_sec: float = 60.0) -> float:
    """Poll budget for epoch-pinned private pool API before page binding (parallel SHPOIB)."""
    active_leases = 0
    parallel_tests = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import parallel_active_test_count

        parallel_tests = parallel_active_test_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
    load = max(active_leases, parallel_tests)
    scaled = max(base_sec, 60.0 + load * 25.0)
    return min(scaled, 180.0)


def e2e_parallel_config_api_timeout_sec(base_sec: float) -> float:
    """Scale omni-config API timeouts under parallel chrome_e2e load (Phase C ramp SSOT)."""
    active_leases = 0
    parallel_tests = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import parallel_active_test_count

        parallel_tests = parallel_active_test_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
    load = max(active_leases, parallel_tests)
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
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
    floor = max(base_sec, 280.0)
    scaled = floor + load * 35.0
    return min(scaled, 600.0)


def signoff_parallel_desktop_progress_api_wall_sec(base_sec: float = 15.0) -> float:
    """Extend desktop progress API poll wall under parallel desktop soak."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base_sec
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() not in ("1", "true", "yes"):
        return base_sec
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
        mux_peers = 0
    load = max(active_leases, parallel_tests, mux_peers)
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
    active_leases = 0
    parallel_tests = 0
    mux_peers = 0
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        active_leases = wave_active_lease_count(MONOREPO_ROOT)
    except (ImportError, OSError, RuntimeError):
        active_leases = 0
    try:
        from mux.transport_supervisor import (
            parallel_active_test_count,
            parallel_mux_peer_count,
        )

        parallel_tests = parallel_active_test_count()
        mux_peers = parallel_mux_peer_count()
    except (ImportError, OSError, RuntimeError):
        parallel_tests = 0
        mux_peers = 0
    return max(active_leases, parallel_tests, mux_peers)


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
