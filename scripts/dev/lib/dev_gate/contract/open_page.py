"""Budgets of opening a page under signoff: parallel wall caps, MCP open budgets, new-page join and shpoib rebind waits."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from dev_gate.contract import parallel_pressure
from dev_gate.contract.wall_clock import (
    _SIGNOFF_TRUTHY,
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    is_e2e_signoff_runtime,
    signoff_effective_bootstrap_wall_sec,
)

# signoff READ SHPOIB open/rebind wall budgets (must precede stall-cap helpers).
SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC: Final[int] = 180
SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC: Final[int] = 240
SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC: Final[int] = 420
SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC: Final[int] = 420
SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC: Final[int] = 600


def _signoff_open_page_parallel_wall_cap() -> float:
    cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC)
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        cap = max(cap, 600.0)
    elif is_e2e_signoff_runtime():
        # panel signoff legs hit join=420 HARD_DEADLINE under parallel mux (M3 v6).
        cap = max(cap, 540.0)
    return cap


def _signoff_open_page_parallel_total_cap() -> float:
    cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC)
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        cap = max(cap, 900.0)
    elif is_e2e_signoff_runtime():
        cap = max(cap, 780.0)
    return cap


@dataclass(frozen=True)
class SignoffOpenMcpBudgets:
    """SSOT for signoff open_mcp_page wall/total/attempts + hung-reap transport cap."""

    wall_budget_sec: float
    total_budget_sec: float
    attempt_count: int
    transport_stall_cap_sec: float
    layout_wait_sec: float = float(SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC)


def signoff_open_mcp_budgets(
    *, parallel_peers: int | None = None
) -> SignoffOpenMcpBudgets:
    """Single SSOT for signoff open_mcp budgets (chrome_mcp_e2e + stall_guard + hung-reap)."""
    peers = parallel_peers
    if peers is None:
        peers = parallel_pressure.parallel_signoff_pressure_peers()
    wall_budget = float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC)
    total_budget = float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC)
    wall_cap = _signoff_open_page_parallel_wall_cap()
    total_cap = _signoff_open_page_parallel_total_cap()
    if peers >= 1:
        wall_budget = min(wall_budget + peers * 18.0, wall_cap)
        total_budget = min(total_budget + peers * 30.0, total_cap)
    body_ref = float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)
    if peers >= 4:
        attempts = 2
        per_attempt_cap = max(180.0, (body_ref * 0.45) / float(attempts))
    else:
        attempts = 3 if peers >= 3 else 2
        per_attempt_cap = max(120.0, (body_ref * 0.52) / float(attempts))
    total_budget = min(total_budget, per_attempt_cap)
    wall_ratio = 0.55
    wall_budget = min(
        wall_budget,
        per_attempt_cap * wall_ratio,
    )
    if peers >= 1:
        parallel_floor = 165.0 if peers < 4 else 240.0
        per_attempt_cap = max(per_attempt_cap, parallel_floor)
        total_budget = min(max(total_budget, parallel_floor), total_cap)
        wall_budget = min(max(wall_budget, parallel_floor * wall_ratio), wall_cap)
    body_frac = max(90.0, body_ref * 0.35)
    if peers >= 1:
        body_frac = min(body_frac + peers * 25.0, body_ref * 0.45)
    if peers < 1:
        stall_cap = per_attempt_cap + 30.0
    else:
        stall_cap = max(
            per_attempt_cap + 120.0,
            min(total_budget + 150.0, body_frac),
        )
    stall_cap = min(
        stall_cap,
        (
            720.0
            if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
            else 540.0
        ),
    )
    return SignoffOpenMcpBudgets(
        wall_budget_sec=wall_budget,
        total_budget_sec=total_budget,
        attempt_count=attempts,
        transport_stall_cap_sec=stall_cap,
    )


def signoff_bootstrap_open_mcp_budgets(
    *, parallel_peers: int | None = None
) -> SignoffOpenMcpBudgets:
    """bootstrap open_mcp budgets — SHPOIB/mux queue headroom, not BODY 35%."""
    peers = parallel_peers
    if peers is None:
        peers = parallel_pressure.parallel_signoff_pressure_peers()
    pessimistic = peers >= 2
    from mux.transport_supervisor import bootstrap_wall_cap_sec, mux_upstream_wait_cap

    boot = float(bootstrap_wall_cap_sec(pessimistic=pessimistic))
    mux = float(mux_upstream_wait_cap(pessimistic=pessimistic))
    effective_boot_wall = max(signoff_effective_bootstrap_wall_sec(), boot + mux)
    bootstrap_wall_cap = min(effective_boot_wall * 0.55, 540.0)
    bootstrap_total_cap = min(effective_boot_wall * 0.75, 720.0)
    wall_budget = min(
        bootstrap_wall_cap,
        max(float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC), boot + mux * 0.35),
    )
    total_budget = min(
        bootstrap_total_cap,
        max(float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC), boot + mux * 0.55),
    )
    if peers >= 1:
        wall_budget = min(
            max(wall_budget + peers * 18.0, boot + mux * 0.25),
            bootstrap_wall_cap,
        )
        total_budget = min(
            max(total_budget + peers * 30.0, boot + mux * 0.45),
            bootstrap_total_cap,
        )
    attempts = 2 if peers >= 4 else 3 if peers >= 3 else 2
    stall_cap = min(max(total_budget + mux * 0.25, boot + mux), bootstrap_total_cap)
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        attempts = max(attempts, 3)
        stall_cap = min(stall_cap * 1.25, bootstrap_total_cap * 1.1)
        total_budget = min(total_budget * 1.15, bootstrap_total_cap)
        wall_budget = min(wall_budget * 1.15, bootstrap_wall_cap)
    return SignoffOpenMcpBudgets(
        wall_budget_sec=wall_budget,
        total_budget_sec=total_budget,
        attempt_count=attempts,
        transport_stall_cap_sec=stall_cap,
    )


def signoff_new_page_join_timeout_sec(
    *,
    page_timeout_ms: int,
    parallel_peers: int | None = None,
) -> float:
    """signoff threaded new_page join — mux queue + page timeout headroom under parallel."""
    mux_grace = page_timeout_ms / 1000.0 + 5.0
    peers = parallel_peers
    if peers is None:
        peers = parallel_pressure.parallel_signoff_pressure_peers()
    load = peers
    try:
        from mux.transport_supervisor import parallel_mux_peer_count

        load = max(load, parallel_mux_peer_count())
    except ImportError:
        pass
    try:
        from mux.load import snapshot_mux_load

        snap = snapshot_mux_load()
        load = max(load, int(snap.mux_contexts), int(snap.wave_leases))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if load < 1:
        solo = signoff_open_mcp_budgets(parallel_peers=0)
        base = max(mux_grace, solo.wall_budget_sec)
        return min(base, float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC))
    parallel_wall = min(
        float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC) + max(0, int(load)) * 18.0,
        _signoff_open_page_parallel_wall_cap(),
    )
    parallel_total = min(
        float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC) + max(0, int(load)) * 30.0,
        _signoff_open_page_parallel_total_cap(),
    )
    open_mcp_wall = signoff_open_mcp_budgets(
        parallel_peers=max(0, int(load)),
    ).wall_budget_sec
    # join must survive open_mcp wall + mux grace (Run#6 desktop join=240s after open_mcp=231s).
    open_mcp_aligned = open_mcp_wall + mux_grace + 30.0
    base = max(mux_grace, parallel_wall, open_mcp_aligned)
    scaled = max(base, 120.0 + load * 15.0)
    floor = max(scaled, parallel_wall * 0.95, open_mcp_aligned)
    cap = min(
        max(floor, parallel_total * 0.55, open_mcp_aligned),
        _signoff_open_page_parallel_wall_cap(),
    )
    result = min(floor, cap)
    if is_e2e_signoff_runtime():
        if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
            desktop_scaled = max(result, 540.0, 120.0 + load * 25.0)
            return min(desktop_scaled, _signoff_open_page_parallel_wall_cap())
        # panel stdin legs under parallel mux (no desktop soak env).
        panel_scaled = max(result, 480.0, 120.0 + load * 22.0)
        return min(panel_scaled, _signoff_open_page_parallel_wall_cap())
    return result


def signoff_new_page_join_stall_abandon_sec(
    *,
    join_timeout_sec: float,
    parallel_peers: int | None = None,
) -> float:
    """abandon hung threaded new_page early under parallel mux queue starvation."""
    peers = parallel_peers
    if peers is None:
        peers = parallel_pressure.parallel_signoff_pressure_peers()
    base = 120.0 + max(0, int(peers)) * 20.0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        base = max(base, 180.0)
    elif is_e2e_signoff_runtime():
        base = max(base, 240.0)
    stall_cap = 300.0
    if os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY:
        stall_cap = 420.0
    elif is_e2e_signoff_runtime():
        stall_cap = 360.0
    return min(join_timeout_sec, min(base, stall_cap))


def shpoib_rebind_location_wait_cap_sec() -> float:
    """SHPOIB navigate location settle; signoff scales under parallel shared-UI compile."""
    if not is_e2e_signoff_runtime():
        return 45.0
    base = float(SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC)
    active_leases = parallel_pressure.wave_active_lease_count_for_mux()
    if active_leases >= 2:
        scaled = base + active_leases * 20.0
        return min(float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC), scaled)
    return base


SIGNOFF_SHPOIB_REBIND_WALL_SEC: Final[int] = 300
SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC: Final[int] = 120
