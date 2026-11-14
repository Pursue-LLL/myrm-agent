"""Admission and submit budgets: wave open, stack recovery, the provider readiness gate, the Dev Gate submit and teardown
timeouts, clarify and desktop-open waits."""

from __future__ import annotations

import os
from typing import Final

from dev_gate.contract import parallel_pressure
from dev_gate.contract.attach import SHARED_ATTACH_RECOVERY_WAIT_SEC, attach_parallel_wait_sec
from dev_gate.contract.mux import MUX_ADMISSION_WAIT_LEASE_SEC, MUX_UPSTREAM_WAIT_SEC
from dev_gate.contract.wall_clock import (
    _SIGNOFF_TRUTHY,
    E2E_ADMISSION_WALL_CLOCK_SEC,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF,
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
    E2E_TEARDOWN_FINISH_CLIENT_TIMEOUT_SEC,
    E2E_TEARDOWN_WALL_CLOCK_SEC,
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC,
    boot_mux_body_transport_gate_required,
    is_desktop_soak_signoff_runtime,
    is_e2e_signoff_runtime,
)

# bootstrap provider readiness gate scales under parallel (align desktop runner 180s).
PROVIDER_READINESS_GATE_BASE_SEC: Final[float] = 60.0
PROVIDER_READINESS_GATE_LEASE_SCALE_SEC: Final[float] = 15.0
PROVIDER_READINESS_GATE_MAX_SEC: Final[float] = 180.0
# desktop leg soak — shared backend config_load_timeout under parallel chrome_e2e.
PROVIDER_READINESS_GATE_DESKTOP_SOAK_LEASE_SCALE_SEC: Final[float] = 40.0
PROVIDER_READINESS_GATE_DESKTOP_SOAK_MAX_SEC: Final[float] = 480.0


def signoff_wave_open_wait_sec() -> int:
    """bounded wait when parallel pytest holds wave with foreign runtimeId."""
    if not is_e2e_signoff_runtime():
        return 0
    return E2E_ADMISSION_WALL_CLOCK_SEC


def signoff_stack_recovery_admit_budget_sec(
    *,
    active_leases: int | None = None,
) -> int:
    """ADMIT fail-fast cap must cover E2E_SHARED_STACK_RECOVERY_WAIT.

    Stack recovery uses attach_parallel_wait_sec; solo admit cap (300–480s) must not
    trip E2E_WALL_BUDGET_FAIL_FAST while recovery still has budget (e.g. 240/660s).
    """
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    leases = (
        active_leases
        if active_leases is not None
        else parallel_pressure.parallel_signoff_pressure_peers()
    )
    return attach_parallel_wait_sec(leases, base=SHARED_ATTACH_RECOVERY_WAIT_SEC)


def provider_readiness_gate_wait_sec(*, active_leases: int | None = None) -> float:
    """Bootstrap provider readiness poll budget (cdp bootstrap gate SSOT).

    Solo 60s; under parallel wave load min(180, 60+leases×15)s — aligns
    ``run_desktop_approval_chrome_e2e`` entry probe and avoids
    ``config_load_timeout`` flakes when shared backend is busy.
    """
    leases = (
        active_leases if active_leases is not None else parallel_pressure.parallel_chrome_e2e_pressure()
    )
    if leases <= 0:
        return PROVIDER_READINESS_GATE_BASE_SEC
    scaled = (
        PROVIDER_READINESS_GATE_BASE_SEC
        + leases * PROVIDER_READINESS_GATE_LEASE_SCALE_SEC
    )
    base_result = min(PROVIDER_READINESS_GATE_MAX_SEC, scaled)
    if (
        os.environ.get("MYRM_E2E_DESKTOP_SOAK", "").strip() in _SIGNOFF_TRUTHY
        and is_e2e_signoff_runtime()
    ):
        load = max(leases, parallel_pressure.parallel_signoff_pressure_peers())
        desktop_scaled = (
            PROVIDER_READINESS_GATE_BASE_SEC
            + load * PROVIDER_READINESS_GATE_DESKTOP_SOAK_LEASE_SCALE_SEC
        )
        return min(
            PROVIDER_READINESS_GATE_DESKTOP_SOAK_MAX_SEC,
            max(base_result, desktop_scaled),
        )
    return base_result


def provider_readiness_gate_effective_budget_sec(
    *,
    phase: str,
    remaining_wall_sec: float,
    bootstrap_cap: float,
) -> float:
    """Resolve provider gate wait budget (desktop soak wall-starve fix).

    Under parallel chrome_e2e, open_mcp_page consumes bootstrap/body wall before
    cdp_bootstrap provider polling. Desktop soak must not clamp gate wait below
    ``provider_readiness_gate_wait_sec`` SSOT.
    """
    scaled = provider_readiness_gate_wait_sec()
    wall_cap = remaining_wall_sec if phase == "body" else bootstrap_cap
    if is_desktop_soak_signoff_runtime():
        wall_cap = max(wall_cap, scaled)
    return max(5.0, min(scaled, wall_cap))


def signoff_hitl_pin_max_attempts(*, active_leases: int | None = None) -> int:
    """HITL securityConfig pin retries under signoff parallel load."""
    base = 3
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return base
    budget = provider_readiness_gate_wait_sec(active_leases=active_leases)
    return max(base, min(9, int(budget // 25) + base))


def signoff_hitl_pin_request_timeout_sec(*, active_leases: int | None = None) -> float:
    """Per-request timeout for HITL pin loopback calls under signoff."""
    if os.environ.get("E2E_SIGNOFF", "").strip() != "1":
        return 15.0
    budget = provider_readiness_gate_wait_sec(active_leases=active_leases)
    return min(45.0, max(15.0, budget / 5))


def _scaled_parallel_admit_wait_sec(*, solo_base: int) -> int:
    """Parallel ADMIT/mux wait: min(900, solo_base + peers×45)."""
    pressure = parallel_pressure.parallel_signoff_pressure_peers()
    if pressure <= 0:
        return solo_base
    scaled = solo_base + pressure * MUX_ADMISSION_WAIT_LEASE_SEC
    return min(E2E_ADMISSION_WALL_CLOCK_SEC, scaled)


def admit_wall_clock_sec() -> int:
    """Fixed ADMIT hard cap: PRIVATE ≤900s; formal signoff ≤300s.

    Parallel pressure is handled by explicit credits and queues. Extending this
    deadline with peer count hides stalls and violates the product contract.
    """
    if is_e2e_signoff_runtime():
        return E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    return E2E_ADMISSION_WALL_CLOCK_SEC


def signoff_read_shpoib_body_wall_sec() -> int:
    """Signoff BODY uses the same non-scalable 600s hard cap."""
    return LIVE_SINGLE_TEST_WALL_CLOCK_SEC


def signoff_effective_body_wall_sec() -> int:
    """Runtime signoff BODY hard cap; never scales with peers or workload."""
    return LIVE_SINGLE_TEST_WALL_CLOCK_SEC


DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC: Final[int] = 60


def dev_gate_post_admit_hard_timeout_sec() -> int:
    """PREPARING+ coordinator budget after PRIVATE admit grant (bootstrap + BODY + teardown).

    tools_panel log-8: grant used now+600 while bootstrap cap=990 + BODY=660 remained;
    HARD_DEADLINE @ ~709s from submit → PARENT_LEASE_NOT_ACTIVE during mux recovery.

    Submit/ADMIT paths must not call live mux snapshot (snapshot_mux_load force=True)
    — parallel chrome_e2e blocks on mux RPC and stalls dev_gate submit wrapper.
    """
    bootstrap_sec = int(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV)
    try:
        from mux.transport_supervisor import (
            MUX_BOOTSTRAP_WALL_MAX_SEC,
            MUX_UPSTREAM_WAIT_MAX_SEC,
        )

        bootstrap_sec = int(MUX_BOOTSTRAP_WALL_MAX_SEC + MUX_UPSTREAM_WAIT_MAX_SEC)
    except ImportError:
        bootstrap_sec = int(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV + MUX_UPSTREAM_WAIT_SEC)
    return (
        bootstrap_sec
        + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
        + E2E_TEARDOWN_WALL_CLOCK_SEC
        + DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC
    )


def dev_gate_submit_hard_timeout_sec() -> int:
    """Coordinator hard_deadline offset from session submit.

    Submit deadline must cover ADMIT queue + bootstrap + effective BODY + teardown.
    """
    if is_desktop_soak_signoff_runtime():
        body = signoff_effective_body_wall_sec()
        return (
            admit_wall_clock_sec()
            + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
            + body
            + E2E_TEARDOWN_WALL_CLOCK_SEC
            + DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC
        )
    if is_e2e_signoff_runtime():
        return (
            admit_wall_clock_sec()
            + SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC
            + DEV_GATE_SUBMIT_HARD_TIMEOUT_GRACE_SEC
        )
    return admit_wall_clock_sec() + dev_gate_post_admit_hard_timeout_sec()


def dev_gate_teardown_finish_client_timeout_sec() -> int:
    """Socket + subprocess budget for teardown-finish under parallel SQLite contention."""
    return E2E_TEARDOWN_FINISH_CLIENT_TIMEOUT_SEC


def dev_bootstrap_wall_cap_for_hung_reap(*, lane: str, shpoib: bool) -> float:
    """hung-reap bootstrap cap must match resolve_budget_policy().bootstrap_sec."""
    bootstrap_sec = float(E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV)
    normalized_lane = lane.strip().upper()
    try:
        from mux.transport_supervisor import (
            bootstrap_wall_cap_sec,
            mux_upstream_wait_cap,
        )

        if (
            boot_mux_body_transport_gate_required()
            or shpoib
            or normalized_lane in {"LIVE_AGENT", "RESOURCE_WRITE"}
        ):
            bootstrap_sec = float(bootstrap_wall_cap_sec(pessimistic=True))
            bootstrap_sec += float(mux_upstream_wait_cap(pessimistic=True))
        else:
            bootstrap_sec = float(bootstrap_wall_cap_sec())
    except ImportError:
        pass
    return bootstrap_sec


def clarify_skip_api_wait_sec() -> int:
    """Clarify form/API pending wait budget; signoff uses shorter fail-fast window."""
    if is_e2e_signoff_runtime():
        return SIGNOFF_CLARIFY_SKIP_API_WAIT_SEC
    return CLARIFY_SKIP_API_WAIT_SEC


# SHPOIB clarify skip API poll under parallel load (API-first path).
CLARIFY_SKIP_API_WAIT_SEC: Final[int] = 180
# E2E signoff: clarify skip API poll under parallel load.
SIGNOFF_CLARIFY_SKIP_API_WAIT_SEC: Final[int] = 300

# mux cold-attach queue + bind_lease under parallel (≤ ADMIT + reclaim).
# mux cold-attach + bind_lease under parallel (≤ 3× ADMIT queue budget).
SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC * 3
)
# parallel signoff desktop — per-strategy wall (must match SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC).
SIGNOFF_DESKTOP_OPEN_NAV_PARALLEL_ATTEMPT_WALL_SEC: Final[int] = 240
# signoff open uses direct + direct_recover retries (see infra_retry strategies).
SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT: Final[int] = 3


def signoff_desktop_open_nav_attempt_wall_sec(*, parallel_peers: int) -> float:
    """Per-strategy asyncio wall for signoff desktop open/nav.

    Solo signoff keeps the full mux-queue budget per attempt. Under parallel mux
    (peers≥2) use a shorter per-attempt wall so scoped attach restart runs between
    tries instead of one 900s new_page hang.
    """
    if parallel_peers >= 2:
        return float(SIGNOFF_DESKTOP_OPEN_NAV_PARALLEL_ATTEMPT_WALL_SEC)
    return float(SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC)
