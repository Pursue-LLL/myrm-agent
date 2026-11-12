"""Wall-clock budgets, attempt counts and retry policy for opening a page."""

from __future__ import annotations

import os
from pathlib import Path

from dev_gate.contract import is_e2e_signoff_runtime

from .parallel_load import _parallel_open_page_peer_count

_OPEN_PAGE_REQUEST_TIMEOUT_SEC = 60.0
_OPEN_PAGE_NEW_PAGE_TIMEOUT_MS = 120_000
_OPEN_PAGE_ATTEMPTS = 2
_OPEN_PAGE_WALL_BUDGET_SEC = 150.0
_OPEN_PAGE_TOTAL_BUDGET_SEC = 280.0
_OPEN_PAGE_BODY_FRACTION = 0.35
_OPEN_PAGE_BODY_FRACTION_WALL_RATIO = 0.55
_OPEN_PAGE_BODY_FRACTION_FLOOR_SEC = 90.0


def _open_page_body_fraction_cap_sec() -> float:
    """open_mcp_page must not consume more than 35% of LIVE BODY wall."""
    try:
        if is_e2e_signoff_runtime():
            from dev_gate.contract import signoff_effective_body_wall_sec

            body_cap = float(signoff_effective_body_wall_sec())
        else:
            from mux.transport_supervisor import live_agent_body_wall_cap_sec

            body_cap = float(live_agent_body_wall_cap_sec())
    except ImportError:
        body_cap = 600.0
    base = max(
        _OPEN_PAGE_BODY_FRACTION_FLOOR_SEC,
        body_cap * _OPEN_PAGE_BODY_FRACTION,
    )
    peers = _parallel_open_page_peer_count()
    if peers >= 2:
        return min(base + peers * 25.0, body_cap * 0.45)
    return base


def _shared_read_parallel_open_page_retry_allowed() -> bool:
    """SHARED READ lane needs mux reload-heal under parallel SMP defer (blank shell)."""
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    if lane != "READ":
        return False
    return os.environ.get("MYRM_E2E_SHARED_HOT", "").strip() != "1"


def _open_page_parallel_retry_allowed() -> bool:
    """Signoff, dev PRIVATE SHPOIB bootstrap, and SHARED READ share mux-heal retry under parallel peers."""
    return is_e2e_signoff_runtime() or _dev_private_shpoib_bootstrap_phase() or _shared_read_parallel_open_page_retry_allowed()


def _open_page_attempt_count() -> int:
    """TPMc: parallel mux — single outer pass; no retry that resets session clock."""
    peers = _parallel_open_page_peer_count()
    if _open_page_parallel_retry_allowed():
        # heavy mux — fewer attempts, more wall per attempt beats 3× short stalls.
        if peers >= 4:
            return 2
        if peers >= 3:
            return 3
        return 2
    if peers >= 2:
        return 1
    return _OPEN_PAGE_ATTEMPTS


def _mux_transport_wait_budget_sec() -> float:
    """Mux queue wait — pessimistic under signoff bootstrap parallel."""
    try:
        from dev_gate.contract import signoff_mux_transport_wait_budget_sec

        return signoff_mux_transport_wait_budget_sec()
    except ImportError:
        from mux.transport_supervisor import mux_upstream_wait_cap

        return float(mux_upstream_wait_cap())


def _shared_read_bootstrap_phase() -> bool:
    """Dev SHARED READ bootstrap — mux queue must not consume open_mcp_page attempt budget."""
    if os.environ.get("MYRM_E2E_LANE", "").strip().upper() != "READ":
        return False
    if os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper() != "SHARED":
        return False
    try:
        from e2e_session_runtime.lifecycle import current_phase

        return current_phase() == "bootstrap"
    except ImportError:
        return False


def _open_page_queue_wait_extends_deadlines() -> bool:
    """P0-C: bootstrap mux fair-queue wait must not consume open_mcp_page attempt budget."""
    if _dev_private_shpoib_bootstrap_phase():
        return True
    if _shared_read_bootstrap_phase():
        return True
    if is_e2e_signoff_runtime():
        try:
            from e2e_session_runtime.lifecycle import current_phase

            return current_phase() == "bootstrap"
        except ImportError:
            return False
    return False


def _extend_open_page_deadlines_for_queue_wait(
    *,
    elapsed_sec: float,
    transport_session_started: float,
    wall_deadline: float,
    total_deadline: float,
) -> tuple[float, float, float]:
    if elapsed_sec <= 0.0 or not _open_page_queue_wait_extends_deadlines():
        return transport_session_started, wall_deadline, total_deadline
    return (
        transport_session_started,
        wall_deadline + elapsed_sec,
        total_deadline + elapsed_sec,
    )


def _dev_private_shpoib_bootstrap_phase() -> bool:
    try:
        from dev_gate.contract import private_shpoib_runtime_active
        from e2e_session_runtime.lifecycle import current_phase

        return current_phase() == "bootstrap" and private_shpoib_runtime_active()
    except ImportError:
        return False


def _open_page_parallel_budgets(
    request_timeout_sec: float,
    *,
    new_page_timeout_ms: int,
    peers: int | None = None,
) -> tuple[float, int, float, float, int]:
    """Fixed open_mcp_page budgets — scale tool wall under parallel mux contention."""
    del peers
    capped_ms = min(new_page_timeout_ms, _OPEN_PAGE_NEW_PAGE_TIMEOUT_MS)
    signoff = is_e2e_signoff_runtime()
    parallel_peers = _parallel_open_page_peer_count()
    if signoff:
        from dev_gate.contract import (
            signoff_bootstrap_open_mcp_budgets,
            signoff_open_mcp_budgets,
        )

        bootstrap_phase = False
        try:
            from e2e_session_runtime.lifecycle import current_phase

            bootstrap_phase = current_phase() == "bootstrap"
        except ImportError:
            bootstrap_phase = False
        if bootstrap_phase:
            budgets = signoff_bootstrap_open_mcp_budgets(parallel_peers=parallel_peers)
        else:
            budgets = signoff_open_mcp_budgets(parallel_peers=parallel_peers)
        wall_budget = budgets.wall_budget_sec
        total_budget = budgets.total_budget_sec
        attempts = budgets.attempt_count
        if parallel_peers >= 2 and not bootstrap_phase:
            body_frac_cap = _open_page_body_fraction_cap_sec()
            total_budget = min(total_budget, body_frac_cap)
            wall_budget = min(
                wall_budget,
                body_frac_cap * _OPEN_PAGE_BODY_FRACTION_WALL_RATIO,
            )
        return (
            min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
            capped_ms,
            wall_budget,
            total_budget,
            attempts,
        )
    if _dev_private_shpoib_bootstrap_phase():
        from dev_gate.contract import signoff_bootstrap_open_mcp_budgets

        budgets = signoff_bootstrap_open_mcp_budgets(parallel_peers=parallel_peers)
        return (
            min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
            capped_ms,
            budgets.wall_budget_sec,
            budgets.total_budget_sec,
            budgets.attempt_count,
        )
    burst_raw = os.environ.get("MYRM_E2E_PHASE_C_BURST_LANES", "").strip()
    if burst_raw.isdigit() and int(burst_raw) >= 4:
        from dev_gate.contract import signoff_open_mcp_budgets

        budgets = signoff_open_mcp_budgets(parallel_peers=int(burst_raw))
        return (
            min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
            capped_ms,
            budgets.wall_budget_sec,
            budgets.total_budget_sec,
            budgets.attempt_count,
        )
    wall_budget = _OPEN_PAGE_WALL_BUDGET_SEC
    total_budget = _OPEN_PAGE_TOTAL_BUDGET_SEC
    wall_cap = 300.0
    total_cap = 480.0
    attempts = _open_page_attempt_count()
    if parallel_peers >= 2:
        wall_budget = min(wall_budget + parallel_peers * 18.0, wall_cap)
        total_budget = min(total_budget + parallel_peers * 30.0, total_cap)
        body_frac_cap = _open_page_body_fraction_cap_sec()
        total_budget = min(total_budget, body_frac_cap)
        wall_budget = min(
            wall_budget,
            body_frac_cap * _OPEN_PAGE_BODY_FRACTION_WALL_RATIO,
        )
    return (
        min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
        capped_ms,
        wall_budget,
        total_budget,
        attempts,
    )


def _should_skip_attach_preflight_restart() -> bool:
    """P0-B: global mux attach restart must not run under active parallel load."""
    try:
        from mux.load import snapshot_mux_load

        load = snapshot_mux_load(force=True)
        if max(0, load.mux_contexts, load.wave_leases) > 0:
            return True
    except (ImportError, OSError, TypeError, ValueError):
        pass
    return _parallel_open_page_peer_count() >= 2


def _open_page_parallel_total_wall_only() -> bool:
    """parallel mux — one outer total_deadline, no per-tool slice starvation."""
    return _parallel_open_page_peer_count() >= 2


def _signoff_mux_drain_budget_sec() -> float:
    """Peers-scaled mux drain budget; signoff bootstrap uses remaining wall (Phase3-C)."""
    budget = _mux_cold_attach_drain_budget_sec()
    if not is_e2e_signoff_runtime():
        return budget
    peers = _parallel_open_page_peer_count()
    if peers >= 1:
        try:
            from dev_gate.contract import signoff_open_mcp_budgets

            budget = max(
                budget,
                signoff_open_mcp_budgets(parallel_peers=peers).wall_budget_sec,
            )
        except ImportError:
            pass
    try:
        from e2e_session_runtime.lifecycle import current_phase, remaining_wall_sec

        if current_phase() == "bootstrap" and peers < 1:
            remaining = remaining_wall_sec()
            if remaining > 0:
                budget = min(max(budget, 45.0), remaining)
    except (ImportError, RuntimeError, TypeError, ValueError):
        pass
    return budget


def _open_page_cdp_probe_budget_sec() -> float:
    """Scale CDP+mux preflight budget under parallel wave/mux load."""
    base = 45.0
    max_budget = 240.0 if is_e2e_signoff_runtime() else 180.0
    peers = 0
    try:
        from mux.load import snapshot_mux_load

        load = snapshot_mux_load()
        peers = max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if peers <= 0:
        monorepo_root = Path(__file__).resolve().parents[5]
        try:
            from e2e_core.stack_mutation_policy import wave_active_lease_count

            peers = wave_active_lease_count(monorepo_root)
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
    if peers <= 0:
        return base
    return min(base + peers * 12.0, max_budget)


def _mux_cold_attach_drain_budget_sec() -> float:
    from dev_gate.contract import parallel_mux_cold_attach_drain_sec

    return parallel_mux_cold_attach_drain_sec(
        parallel_peers=_parallel_open_page_peer_count(),
    )
