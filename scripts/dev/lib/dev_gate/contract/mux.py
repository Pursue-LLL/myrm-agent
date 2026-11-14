"""Mux timeouts and the budgets that scale with mux load: request timeouts, responsive-probe and page-reclaim budgets,
upstream waits."""

from __future__ import annotations

import os
from typing import Final

from dev_gate.contract import parallel_pressure
from dev_gate.contract.wall_clock import (
    _SIGNOFF_TRUTHY,
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
    is_e2e_signoff_runtime,
    signoff_effective_bootstrap_wall_sec,
)

MUX_COLD_ATTACH_TIMEOUT_MS: Final[int] = 30_000
CDMCP_MUX_REQUEST_TIMEOUT_MS_DEFAULT: Final[int] = 180_000
LEGACY_MUX_REQUEST_TIMEOUT_MS: Final[tuple[int, ...]] = (55_000, 65_000, 120_000)
# mux tools/list probe budget during attach/bootstrap (align chrome-e2e-preflight.sh).
MUX_RESPONSIVE_PROBE_BASE_SEC: Final[float] = 8.0
MUX_RESPONSIVE_PROBE_LEASE_SCALE_SEC: Final[float] = 3.0
MUX_RESPONSIVE_PROBE_MAX_SEC: Final[float] = 45.0
MUX_RESPONSIVE_PROBE_RETRY_ATTEMPTS: Final[int] = 3

# Physical work is bounded; logical shared sessions are deliberately unlimited.
# Mux ADMIT wait scales with active wave leases (align attach scaling).
MUX_ADMISSION_WAIT_LEASE_SEC: Final[int] = 45
MUX_UPSTREAM_WAIT_SEC: Final[int] = 300
MUX_UPSTREAM_POLL_SEC: Final[int] = 15


def mux_reset_after_orphan_timeout_sec() -> float:
    """Scale asyncio wait_for around reset_after_orphan under parallel mux load.

    v9 died at hardcoded 90s while peers≥6; align with shpoib_parallel_stall scaling.
    desktop leg soak extends cap to 300s under parallel chrome_e2e.
    """
    base = 90.0
    active_leases = 0
    try:
        from pathlib import Path

        from e2e_core.stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[6]
        active_leases = wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        active_leases = 0
    if active_leases < 2:
        scaled = base
    else:
        scaled = min(180.0, base + active_leases * 10.0)
    if (
        os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
        and is_e2e_signoff_runtime()
    ):
        load = max(active_leases, parallel_pressure.parallel_signoff_pressure_peers())
        desktop_scaled = base + load * 20.0
        return min(300.0, max(scaled, desktop_scaled))
    if is_e2e_signoff_runtime():
        # parallel signoff post-SEND_TURN attach needs mux reclaim headroom (v146 @45s, v153 @180s).
        peers = max(active_leases, parallel_pressure.parallel_signoff_pressure_peers())
        if peers >= 2:
            return min(300.0, max(scaled, 60.0 + peers * 15.0))
        return min(scaled, 60.0)
    return scaled


def mux_responsive_probe_timeout_sec(*, active_leases: int | None = None) -> float:
    """tools/list probe budget for mux stamp validation (preflight + test.sh SSOT).

    Solo 8s; under parallel wave load min(45, 8+leases×3)s — matches
    chrome-e2e-preflight.sh ``_mux_probe_timeout_sec``.
    """
    leases = (
        active_leases
        if active_leases is not None
        else parallel_pressure.wave_active_lease_count_for_mux()
    )
    if leases <= 0:
        return MUX_RESPONSIVE_PROBE_BASE_SEC
    scaled = (
        MUX_RESPONSIVE_PROBE_BASE_SEC + leases * MUX_RESPONSIVE_PROBE_LEASE_SCALE_SEC
    )
    return min(MUX_RESPONSIVE_PROBE_MAX_SEC, scaled)


def parallel_mux_cold_attach_drain_sec(*, parallel_peers: int | None = None) -> float:
    """Peers-scaled mux cold-attach drain budget (open_mcp_page + infra_retry SSOT).

    Signoff uses the same floor as dev (fixes historical 20s<45s inversion).
    """
    from mux.transport_supervisor import mux_upstream_wait_cap

    peers = parallel_peers
    if peers is None:
        peers = parallel_pressure.parallel_signoff_pressure_peers()
    base = 45.0
    scaled = base + max(0, int(peers)) * 12.0
    ceiling = float(mux_upstream_wait_cap())
    return min(max(base, scaled), ceiling)


def signoff_mux_transport_wait_budget_sec(
    *, bootstrap_phase: bool | None = None
) -> float:
    """pessimistic mux queue wait under signoff bootstrap parallel."""
    from mux.transport_supervisor import mux_upstream_wait_cap

    pessimistic = False
    if is_e2e_signoff_runtime():
        if bootstrap_phase is None:
            try:
                from e2e_session_runtime.lifecycle import current_phase

                bootstrap_phase = current_phase() == "bootstrap"
            except ImportError:
                bootstrap_phase = False
        if bootstrap_phase and parallel_pressure.parallel_signoff_pressure_peers() >= 2:
            pessimistic = True
    mux_cap = float(mux_upstream_wait_cap(pessimistic=pessimistic))
    if is_e2e_signoff_runtime() and bootstrap_phase:
        return max(mux_cap, signoff_effective_bootstrap_wall_sec() * 0.85)
    return mux_cap


def mux_page_reclaim_hard_timeout_sec() -> int:
    """Mux page reopen/reclaim hard wall; signoff allows parallel mux bind_lease wait."""
    if is_e2e_signoff_runtime():
        return MUX_PAGE_RECLAIM_HARD_TIMEOUT_SIGNOFF_SEC
    return MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC


# --- Adaptive mux load defaults (env may override in mux.load) ---

BASE_PAGE_TIMEOUT_MS: Final[int] = 30_000
PAGE_TIMEOUT_SLOT_MS: Final[int] = 15_000
MAX_PAGE_TIMEOUT_MS: Final[int] = 120_000
BASE_TOOL_TIMEOUT_SEC: Final[float] = 180.0

# hard wall for mux page reopen/reclaim (nested call_tool must not burn 600s).
MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC: Final[int] = 120
# signoff desktop under parallel chrome_e2e may block on bind_lease >120s.
MUX_PAGE_RECLAIM_HARD_TIMEOUT_SIGNOFF_SEC: Final[int] = E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
