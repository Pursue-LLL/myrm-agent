"""Stall caps of transport and admit nodes, the shell-probe fail-fast and the backend-only ensure timeout, with the node
tables they rest on."""

from __future__ import annotations

import os
from typing import Final

from dev_gate.contract import parallel_pressure
from dev_gate.contract.admission import _scaled_parallel_admit_wait_sec, admit_wall_clock_sec
from dev_gate.contract.attach import SIGNOFF_ATTACH_PARALLEL_CAP_SEC
from dev_gate.contract.mux import parallel_mux_cold_attach_drain_sec
from dev_gate.contract.open_page import (
    signoff_bootstrap_open_mcp_budgets,
    signoff_new_page_join_timeout_sec,
    signoff_open_mcp_budgets,
)
from dev_gate.contract.wall_clock import (
    E2E_ADMISSION_WALL_CLOCK_SEC,
    LIVE_AGENT_BODY_WALL_CLOCK_SEC,
    is_desktop_soak_signoff_runtime,
    is_e2e_signoff_runtime,
)

# Holder / progress stale detection while queueing on shared_hot stream.
STALL_PROGRESS_SEC: Final[int] = 90
# LIVE WebUI turns (TURN_WAIT_SEC=300) may legitimately stall snapshot progress >90s.
LIVE_AGENT_STALL_PROGRESS_FLOOR_SEC: Final[int] = 240
# E2E signoff: desktop wait_shell_layout may block on mux evaluate >90s even solo.
SIGNOFF_STALL_PROGRESS_FLOOR_SEC: Final[int] = 150
# Watchdog: expire heartbeat-stale leases (display stale remains STALL_PROGRESS_SEC).
E2E_STALE_HEARTBEAT_REAP_SEC: Final[int] = 45


def shpoib_parallel_stall_progress_sec(
    *,
    lane: str | None = None,
    workload: str | None = None,
) -> float:
    """Scale BODY progress-stale cap under parallel SHPOIB load.

    Matches file_write LIVE scaling: base 90s + 10s per active wave lease (max 150s).
    LIVE_AGENT/RESOURCE_WRITE: floor 240s (LLM turn wait) + 30s/lease (max 360s).
    signoff (incl. desktop soak) extends cap for wait_shell_layout mux evaluate.

    Coordinator hung-reap must pass lane/workload from session snapshot — not its own env.
    """
    base = float(STALL_PROGRESS_SEC)
    lane_val = (lane or os.environ.get("MYRM_E2E_LANE", "")).strip().upper()
    workload_val = (workload or os.environ.get("MYRM_E2E_WORKLOAD", "")).strip().upper()
    is_live_lane = (
        lane_val in {"LIVE_AGENT", "RESOURCE_WRITE"} or workload_val == "LIVE"
    )
    if is_live_lane:
        base = max(base, float(LIVE_AGENT_STALL_PROGRESS_FLOOR_SEC))
    active_leases = 0
    try:
        from pathlib import Path

        from e2e_core.stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[6]
        active_leases = wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        active_leases = 0
    if is_e2e_signoff_runtime():
        load = max(active_leases, parallel_pressure.parallel_signoff_pressure_peers())
        scaled = base + load * 15.0
        return min(240.0, max(float(SIGNOFF_STALL_PROGRESS_FLOOR_SEC), scaled))
    if os.environ.get("MYRM_E2E_SHPOIB", "").strip() != "1":
        return base
    if active_leases < 2:
        return base
    if is_live_lane:
        return min(360.0, base + active_leases * 30.0)
    return min(150.0, base + active_leases * 10.0)


def shell_probe_stall_fail_fast_effective_sec() -> float:
    """Scale skeleton/blank shell fail-fast under parallel signoff desktop soak."""
    base = float(SHELL_PROBE_STALL_FAIL_FAST_SEC)
    if not (
        is_desktop_soak_signoff_runtime()
        or os.environ.get("E2E_SIGNOFF", "").strip() == "1"
    ):
        return base
    try:
        from cdp_chat.support import signoff_parallel_force_chat_timeout_sec

        return signoff_parallel_force_chat_timeout_sec(base)
    except ImportError:
        return base


def signoff_bootstrap_transport_stall_cap_sec(
    *,
    parallel_peers: int | None = None,
    page_timeout_ms: int = 90_000,
) -> float:
    """bootstrap open_mcp stall cap — must cover parallel new_page join.

    ``total_budget_sec`` is per-attempt open_mcp wall; transport stall must not be
    clamped below parallel-scaled threaded join (hung-reap + chrome_mcp_e2e SSOT).
    """
    budgets = signoff_bootstrap_open_mcp_budgets(parallel_peers=parallel_peers)
    join_floor = (
        signoff_new_page_join_timeout_sec(
            page_timeout_ms=page_timeout_ms,
            parallel_peers=parallel_peers,
        )
        + 10.0
    )
    return max(budgets.transport_stall_cap_sec, join_floor)


def signoff_open_page_transport_stall_cap_sec() -> float:
    """Signoff transport-node stall cap aligned with chrome_mcp_e2e open_mcp_page."""
    if not is_e2e_signoff_runtime():
        return float(NODE_STUCK_FAIL_FAST_SEC)
    return signoff_open_mcp_budgets().transport_stall_cap_sec


def live_open_page_transport_stall_cap_sec(*, active_peers: int | None = None) -> float:
    """hung-reap NODE_STUCK cap aligned with chrome_mcp open_mcp body fraction.

    log-11 @121s: peers<2 returned 120s while mux queue still draining — SIGKILL mid open_mcp.
    """
    peers = active_peers
    if peers is None:
        peers = 0
        try:
            from mux.load import (
                active_mux_context_count,
                read_mux_status,
                snapshot_mux_load,
            )

            mux_status = read_mux_status()
            load = snapshot_mux_load()
            peers = max(int(load.wave_leases), active_mux_context_count(mux_status))
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            peers = 0
    try:
        from mux.transport_supervisor import live_agent_body_wall_cap_sec

        body_cap = float(live_agent_body_wall_cap_sec())
    except ImportError:
        body_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
    body_frac = max(
        _OPEN_PAGE_BODY_FRACTION_FLOOR_SEC, body_cap * _OPEN_PAGE_BODY_FRACTION
    )
    drain_floor = float(parallel_mux_cold_attach_drain_sec(parallel_peers=peers))
    solo_floor = max(body_frac, drain_floor, float(NODE_STUCK_FAIL_FAST_SEC))
    if peers < 2:
        return solo_floor
    base = max(_OPEN_PAGE_BODY_FRACTION_FLOOR_SEC, body_cap * _OPEN_PAGE_BODY_FRACTION)
    return min(base + float(peers) * 25.0, body_cap * 0.45)


def is_admit_semantic_stall_node(node: str) -> bool:
    """True for ADMIT phase nodes eligible for node-level stall (below admit process wall)."""
    text = node.strip()
    if not text:
        return False
    return any(text.startswith(prefix) for prefix in ADMIT_SEMANTIC_STALL_NODE_PREFIXES)


def admit_semantic_node_stall_cap_sec(
    *,
    current_node: str,
    batch_mode: bool = False,
    signoff: bool = False,
) -> float:
    """Node-level ADMIT stall cap — releases credit before 900s process wall when stuck.

    E2E_ADMIT_TEST_SH (no sidecar) and batch parent holders must not block parallel
    queue for the full dev ADMIT wall while test.sh never writes a snapshot.
    """
    node = current_node.strip()
    if not is_admit_semantic_stall_node(node):
        return float(E2E_ADMISSION_WALL_CLOCK_SEC)
    uses_tight_cap = node == E2E_ADMIT_TEST_SH_NODE or (
        batch_mode and node.startswith("E2E_ADMIT_")
    )
    if not uses_tight_cap:
        if signoff:
            return float(admit_wall_clock_sec())
        return float(E2E_ADMISSION_WALL_CLOCK_SEC)
    base = float(
        ADMIT_BATCH_PARENT_STALL_CAP_DEV_SEC
        if batch_mode
        else ADMIT_TEST_SH_STALL_CAP_DEV_SEC
    )
    if signoff:
        peers = max(0, parallel_pressure.parallel_signoff_pressure_peers())
        if peers >= 2:
            scaled = _scaled_parallel_admit_wait_sec(solo_base=int(base))
            return min(float(SIGNOFF_ATTACH_PARALLEL_CAP_SEC), scaled)
        return min(float(SIGNOFF_ATTACH_PARALLEL_CAP_SEC), base + 60.0)
    pressure = parallel_pressure.parallel_chrome_e2e_pressure()
    if pressure >= 2:
        return min(480.0, base + float(pressure) * 45.0)
    return base


def resolve_transport_stall_cap_sec(*, current_node: str = "") -> float:
    """SSOT: hung-reap / open_mcp NODE_STUCK cap (import fresh after reload)."""
    try:
        from e2e_core.stall_guard import (
            is_transport_stall_node,
            transport_stall_cap_sec,
        )
    except ImportError:
        return float(NODE_STUCK_FAIL_FAST_SEC)
    transport = transport_stall_cap_sec()
    if not is_transport_stall_node(current_node):
        return transport
    open_page_family = current_node.startswith(("open_mcp_page", "open_page_"))
    if is_e2e_signoff_runtime():
        if open_page_family:
            try:
                from mux.load import parallel_open_page_peer_count

                peers = parallel_open_page_peer_count(signoff=True)
            except ImportError:
                peers = 0
            bootstrap_cap = signoff_bootstrap_transport_stall_cap_sec(
                parallel_peers=peers,
            )
            body_cap = signoff_open_page_transport_stall_cap_sec()
            return max(transport, bootstrap_cap, body_cap)
        return max(transport, signoff_open_page_transport_stall_cap_sec())
    if open_page_family:
        live = live_open_page_transport_stall_cap_sec()
        try:
            from mux.transport_supervisor import live_agent_body_wall_cap_sec

            body_cap = float(live_agent_body_wall_cap_sec())
        except ImportError:
            body_cap = float(LIVE_AGENT_BODY_WALL_CLOCK_SEC)
        body_frac = max(
            _OPEN_PAGE_BODY_FRACTION_FLOOR_SEC,
            body_cap * _OPEN_PAGE_BODY_FRACTION,
        )
        if live <= float(NODE_STUCK_FAIL_FAST_SEC):
            live = body_frac
        elif transport > float(NODE_STUCK_FAIL_FAST_SEC):
            peer_hint = max(
                2,
                round((transport - float(NODE_STUCK_FAIL_FAST_SEC)) / 22.0),
            )
            live = max(
                live, live_open_page_transport_stall_cap_sec(active_peers=peer_hint)
            )
        return max(transport, live, body_frac)
    return transport


def _backend_only_ensure_parallel_load() -> int:
    """Peer pressure for backend-only ensure — wave leases can lag during ADMIT (+)."""
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
    for key in (
        "MYRM_E2E_PARALLEL_ACTIVE_COUNT",
        "MYRM_E2E_PARALLEL_ACTIVE_LEASES",
        "MYRM_E2E_PHASE_C_BURST_LANES",
    ):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            load = max(load, max(0, int(raw) - 1))
    if is_e2e_signoff_runtime():
        try:
            load = max(load, parallel_pressure.parallel_signoff_pressure_peers())
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
        try:
            from mux.transport_supervisor import parallel_mux_peer_count

            load = max(load, parallel_mux_peer_count())
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
    return max(0, load)


def shpoib_backend_only_ensure_parallel_timeout_sec() -> float:
    """Wall timeout for SHPOIB backend-only ensure; scales under parallel chrome_e2e."""
    raw = os.environ.get("MYRM_BACKEND_ONLY_ENSURE_TIMEOUT_SEC", "360")
    try:
        base = max(120.0, float(raw))
    except ValueError:
        base = 360.0
    load = _backend_only_ensure_parallel_load()
    if load < 1:
        return base
    return min(540.0, base + load * 45.0)


def shpoib_backend_only_ensure_stall_cap_sec() -> float:
    """Hung-reap cap for SHPOIB backend-only ensure — must match subprocess timeout SSOT."""
    return shpoib_backend_only_ensure_parallel_timeout_sec()


SHELL_PROBE_STALL_FAIL_FAST_SEC: Final[int] = 120
# browser takeover gate — consecutive MUX stall without API gate progress.
GATE_MUX_STALL_FAIL_FAST_SEC: Final[int] = 120
# transport infra nodes stuck without semantic progress (parallel mux hog).
NODE_STUCK_FAIL_FAST_SEC: Final[int] = GATE_MUX_STALL_FAIL_FAST_SEC
# dev openPageTransaction whole-RPC wall — orchestrator daemon + client socket + hung-reap SSOT.
DEV_OPEN_PAGE_TRANSACTION_WALL_SEC: Final[float] = float(NODE_STUCK_FAIL_FAST_SEC)

TRANSPORT_STALL_NODE_PREFIXES: Final[tuple[str, ...]] = (
    "open_mcp_page_",
    "open_page_",
    "force_chat_shell_",
    "mux_",
    "bootstrap_",
    "bridge_",
    "E2E_BOOTSTRAP",
)
# ADMIT semantic nodes — node-level stall below process admit_wall (900s dev).
ADMIT_SEMANTIC_STALL_NODE_PREFIXES: Final[tuple[str, ...]] = ("E2E_ADMIT_",)
E2E_ADMIT_TEST_SH_NODE: Final[str] = "E2E_ADMIT_TEST_SH"
ADMIT_TEST_SH_STALL_CAP_DEV_SEC: Final[int] = 180
ADMIT_BATCH_PARENT_STALL_CAP_DEV_SEC: Final[int] = 180

# Process-level cap: bootstrap holder blocks private_credit_queue (node hops reset node_elapsed).
BOOTSTRAP_CREDIT_HOG_PROCESS_CAP_SEC: Final[int] = 300
BOOTSTRAP_CREDIT_HOG_NODE_NAMES: Final[frozenset[str]] = frozenset(
    {
        "wait_for_state",
        "wait_for_react_e2e_bridge",
        "wait_for_shell_layout",
        "wait_for_shell_ready",
        "open_page_transaction",
    }
)

ORPHAN_BUDGET_FAIL_SEC: Final[float] = 30.0
ORPHAN_BUDGET_SLACK: Final[int] = 1
_OPEN_PAGE_BODY_FRACTION: Final[float] = 0.35
_OPEN_PAGE_BODY_FRACTION_FLOOR_SEC: Final[float] = 90.0
