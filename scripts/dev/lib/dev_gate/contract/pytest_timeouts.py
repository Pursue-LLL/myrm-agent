"""pytest-timeout budgets of a chrome_e2e run: lane timeouts, floors and ceilings, the signoff outer-kill budgets and the
pytest-safe session timeout."""

from __future__ import annotations

import os
from typing import Final

from dev_gate.contract.admission import (
    SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT,
    SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC,
    admit_wall_clock_sec,
)
from dev_gate.contract.caps import SHARED_BROWSER_WORKERS
from dev_gate.contract.mux import MAX_PAGE_TIMEOUT_MS, MUX_UPSTREAM_WAIT_SEC
from dev_gate.contract.wall_clock import (
    E2E_ADMISSION_WALL_CLOCK_SEC,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF,
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
    E2E_TEARDOWN_WALL_CLOCK_SEC,
    LIVE_AGENT_BODY_WALL_CLOCK_SEC,
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC,
    private_shpoib_runtime_active,
    resolve_e2e_wall_profile,
)

CHROME_E2E_MATRIX_TIMEOUT_SECONDS: Final[int] = 7200
# Single desktop approval chrome_e2e uses the global wall budget (not matrix duration).
CHROME_E2E_DESKTOP_TIMEOUT_SECONDS: Final[int] = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
CHROME_E2E_STRESS_TIMEOUT_SECONDS: Final[int] = 7200
CHROME_E2E_DESKTOP_MARKER: Final[str] = "chrome_e2e_desktop"
CHROME_E2E_BROWSER_TAKEOVER_LIVE_MARKER: Final[str] = "chrome_e2e_browser_takeover_live"
CHROME_E2E_SIGNOFF_BATCH_MARKER: Final[str] = "chrome_e2e_signoff_batch"

# --- Chrome E2E pytest-timeout SSOT (lane-aware; ≥ mux new_page retry window) ---

# pytest-timeout cap for a single LIVE pytest item (bootstrap + body + teardown; ADMIT is pre-pytest).
LIVE_AGENT_PYTEST_WALL_CAP_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    + E2E_TEARDOWN_WALL_CLOCK_SEC
)
# SHPOIB RESOURCE_WRITE: ADMIT (pre-body) + bootstrap + body — observed mono_elapsed≈754s before SHPOIB.
SHPOIB_RESOURCE_WRITE_PYTEST_FLOOR_SEC: Final[int] = (
    E2E_ADMISSION_WALL_CLOCK_SEC + LIVE_AGENT_PYTEST_WALL_CAP_SEC
)
# pytest-timeout floor body segment — SSOT with LIVE_AGENT_BODY_WALL_CLOCK_SEC.
LIVE_AGENT_BODY_BUFFER_SEC: Final[int] = LIVE_AGENT_BODY_WALL_CLOCK_SEC

# desktop pytest spans bootstrap + N× open/nav reserve + fresh BODY after open.
SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC: Final[int] = (
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + SIGNOFF_DESKTOP_OPEN_NAV_WALL_TIMEOUT_SEC
    * SIGNOFF_DESKTOP_OPEN_NAV_STRATEGY_COUNT
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    + E2E_TEARDOWN_WALL_CLOCK_SEC
)

# run_pytest_safe outer budget padding beyond pytest floor (bootstrap/MCP setup).
PYTEST_SAFE_BOOTSTRAP_BUFFER_SEC: Final[int] = 120
# E2E signoff: outer kill aligned with four-phase signoff budgets.
SIGNOFF_PYTEST_SAFE_BUFFER_SEC: Final[int] = 60
SIGNOFF_OUTER_KILL_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
)
# READ SHPOIB signoff panel legs reserve UEA capacity wait inside pytest (func_only=False).
SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC: Final[int] = (
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
    + E2E_ADMISSION_WALL_CLOCK_SEC
    + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
    + LIVE_SINGLE_TEST_WALL_CLOCK_SEC
)
SIGNOFF_READ_SHPOIB_OUTER_KILL_SEC: Final[int] = (
    SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
)

# desktop signoff spans open/nav reserve inside pytest (not quality-gate BODY).
SIGNOFF_DESKTOP_OUTER_KILL_SEC: Final[int] = (
    SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
)
READ_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    MUX_UPSTREAM_WAIT_SEC + MAX_PAGE_TIMEOUT_MS // 1000 + 90
)
LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC: Final[int] = (
    LIVE_AGENT_BODY_BUFFER_SEC + MAX_PAGE_TIMEOUT_MS // 1000 + 90
)
CHROME_E2E_BROWSER_TAKEOVER_PYTEST_TIMEOUT_SEC: Final[int] = (
    LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC
)


def chrome_e2e_pytest_timeout_for_lane(lane: str) -> int:
    """Return pytest-timeout floor for a formal chrome_e2e session lane."""
    if lane.strip().upper() == "READ":
        return READ_CHROME_E2E_PYTEST_TIMEOUT_SEC
    return LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC


def phase_c_burst_lane_count() -> int:
    """Declared Phase C parallel burst width (MYRM_E2E_PHASE_C_BURST_LANES)."""
    raw = os.environ.get("MYRM_E2E_PHASE_C_BURST_LANES", "").strip()
    if not raw.isdigit():
        return 0
    return max(0, int(raw))


def phase_c_burst_read_bootstrap_wall_sec() -> int | None:
    """READ dev bootstrap wall when Phase C burst lanes declare parallel mux pressure."""
    burst_lanes = phase_c_burst_lane_count()
    if burst_lanes < 2:
        return None
    from mux.transport_supervisor import caps_for_explicit_peer_count

    pessimistic = burst_lanes >= 4
    bootstrap, mux_wait = caps_for_explicit_peer_count(
        burst_lanes,
        pessimistic=pessimistic,
    )
    if burst_lanes >= 4:
        return bootstrap + mux_wait
    return bootstrap


def phase_c_burst_read_queue_buffer_sec() -> int:
    """run_pytest_safe queue buffer for Phase C READ burst (mux open_mcp_page queue)."""
    burst_lanes = phase_c_burst_lane_count()
    if burst_lanes < 4:
        return 0
    from mux.transport_supervisor import caps_for_explicit_peer_count

    _, mux_wait = caps_for_explicit_peer_count(burst_lanes, pessimistic=True)
    return mux_wait


def chrome_e2e_pytest_safe_queue_buffer_sec(
    lane: str,
    joined_argv: str,
    *,
    shpoib: bool | None = None,
) -> int:
    """Queue/admission wait excluded from body wall clock but counted by run_pytest_safe."""
    if resolve_e2e_wall_profile() == "signoff":
        return admit_wall_clock_sec()
    private_mode = (
        shpoib
        if shpoib is not None
        else os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip() == "PRIVATE"
    )
    if private_mode:
        return E2E_ADMISSION_WALL_CLOCK_SEC
    burst_buffer = phase_c_burst_read_queue_buffer_sec()
    if burst_buffer > 0 and lane.strip().upper() == "READ":
        return burst_buffer
    del joined_argv
    return 0


def _signoff_read_shpoib_leg(joined_argv: str) -> bool:
    """True when signoff READ lane runs SHPOIB chrome_e2e (panel_stdin legs)."""
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return False
    shpoib = os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    return shpoib and lane == "READ"


def _parse_signoff_batch_body_sec(joined_argv: str) -> int | None:
    """Extract body_sec from chrome_e2e_signoff_batch marker in joined argv."""
    if CHROME_E2E_SIGNOFF_BATCH_MARKER not in joined_argv:
        return None
    for token in joined_argv.split():
        if token.startswith("body_sec="):
            raw = token.split("=", 1)[1]
            if raw.isdigit():
                return int(raw)
    return None


def _signoff_batch_body_sec(joined_argv: str) -> int | None:
    """Batch BODY override from argv marker or MYRM_E2E_SIGNOFF_BATCH_BODY_SEC."""
    batch_body = _parse_signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return batch_body
    batch_env = os.environ.get("MYRM_E2E_SIGNOFF_BATCH_BODY_SEC", "").strip()
    if batch_env.isdigit():
        return int(batch_env)
    return None


def signoff_batch_pytest_timeout_ceiling_sec(body_sec: int) -> int:
    """pytest-timeout for multi-scenario signoff batch legs (+ extended BODY)."""
    return (
        E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC
        + E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF
        + body_sec
        + E2E_TEARDOWN_WALL_CLOCK_SEC
    )


def signoff_pytest_timeout_ceiling_sec(joined_argv: str) -> int:
    """Signoff pytest-timeout ceiling; desktop leg reserves open/nav inside pytest."""
    batch_body = _signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return signoff_batch_pytest_timeout_ceiling_sec(batch_body)
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return SIGNOFF_DESKTOP_PYTEST_TIMEOUT_CEILING_SEC
    if _signoff_read_shpoib_leg(joined_argv):
        return SIGNOFF_READ_SHPOIB_PYTEST_TIMEOUT_CEILING_SEC
    return SIGNOFF_PYTEST_TIMEOUT_CEILING_SEC


def signoff_outer_kill_sec(joined_argv: str) -> int:
    """run_pytest_safe outer budget for signoff chrome_e2e legs."""
    batch_body = _signoff_batch_body_sec(joined_argv)
    if batch_body is not None:
        return (
            signoff_batch_pytest_timeout_ceiling_sec(batch_body)
            + SIGNOFF_PYTEST_SAFE_BUFFER_SEC
        )
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return SIGNOFF_DESKTOP_OUTER_KILL_SEC
    if _signoff_read_shpoib_leg(joined_argv):
        return SIGNOFF_READ_SHPOIB_OUTER_KILL_SEC
    return SIGNOFF_OUTER_KILL_SEC


def chrome_e2e_pytest_safe_timeout_sec(
    lane: str,
    item_count: int,
    joined_argv: str = "",
) -> int:
    """Hard timeout for run_pytest_safe wrapper across a chrome_e2e session."""
    if resolve_e2e_wall_profile() == "signoff":
        return signoff_outer_kill_sec(joined_argv)
    per_item = chrome_e2e_pytest_timeout_floor(lane, joined_argv)
    normalized_count = max(1, int(item_count))
    raw = per_item * normalized_count
    # CHROME_E2E_MATRIX is per long single-test (desktop/matrix); multi-item sessions scale by mux waves.
    wave_cap = CHROME_E2E_MATRIX_TIMEOUT_SECONDS * max(
        1,
        (normalized_count + SHARED_BROWSER_WORKERS - 1) // SHARED_BROWSER_WORKERS,
    )
    queue_buffer = chrome_e2e_pytest_safe_queue_buffer_sec(lane, joined_argv)
    return min(raw, wave_cap) + PYTEST_SAFE_BOOTSTRAP_BUFFER_SEC + queue_buffer


def parallel_live_pytest_timeout_floor_sec(base: int) -> int:
    """Extend pytest-timeout when parallel mux inflates in-test bootstrap.

    Observed: leases=5 bootstrap mono_elapsed≈730s before BODY — 810s floor kills at REAPPLY.
    +: wave_active_lease_count can lag registry peers during ADMIT — include session SSOT.
    """
    load = 0
    try:
        from pathlib import Path

        from e2e_core.stack_mutation_policy import wave_active_lease_count

        load = wave_active_lease_count(Path(__file__).resolve().parents[6])
    except (ImportError, OSError, RuntimeError, ValueError):
        load = 0
    try:
        from e2e_core.peer_count_ssot import parallel_active_test_count_ssot

        session_peers = parallel_active_test_count_ssot()
        load = max(load, max(0, session_peers - 1))
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    if load < 2:
        return base
    scaled = base + int(load) * 180
    return min(1830, max(base, scaled))


def parallel_ramp_pytest_timeout_override_sec() -> int | None:
    """Phase C parallel ramp raises READ solo floor (510s) for mux queue depth."""
    raw = os.environ.get("E2E_PARALLEL_RAMP_PYTEST_TIMEOUT_SEC", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    burst = os.environ.get("MYRM_E2E_PHASE_C_BURST_LANES", "").strip()
    if not burst.isdigit():
        return None
    lanes = int(burst)
    if lanes >= 16:
        return 1200
    if lanes >= 8:
        return 1200
    if lanes >= 4:
        return 1140
    if lanes >= 2:
        return 600
    return None


def chrome_e2e_pytest_timeout_floor(lane: str, joined_argv: str) -> int:
    """Lane floor with marker-aware overrides; SHPOIB admission runs inside pytest fixture."""
    if resolve_e2e_wall_profile() == "signoff":
        return signoff_pytest_timeout_ceiling_sec(joined_argv)
    if CHROME_E2E_DESKTOP_MARKER in joined_argv:
        return CHROME_E2E_DESKTOP_TIMEOUT_SECONDS
    floor = chrome_e2e_pytest_timeout_for_lane(lane)
    private_mode = os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip() == "PRIVATE"
    normalized_lane = lane.strip().upper()
    shpoib = private_shpoib_runtime_active()
    if private_mode and normalized_lane in {"LIVE_AGENT", "READ"}:
        floor = max(floor, LIVE_AGENT_PYTEST_WALL_CAP_SEC)
    elif private_mode and shpoib and normalized_lane == "RESOURCE_WRITE":
        floor = max(
            floor,
            min(1830, SHPOIB_RESOURCE_WRITE_PYTEST_FLOOR_SEC),
        )
    ramp_override = parallel_ramp_pytest_timeout_override_sec()
    if ramp_override is not None:
        floor = max(floor, ramp_override)
    if normalized_lane in {"LIVE_AGENT", "RESOURCE_WRITE"}:
        floor = parallel_live_pytest_timeout_floor_sec(floor)
    return floor
