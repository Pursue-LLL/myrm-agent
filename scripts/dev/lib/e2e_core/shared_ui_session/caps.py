"""Wall-clock caps of the shared UI session contract (bridge-ready cap scaled by host load, deadline extension)
and the hot-path switches that decide how much of the bootstrap is skipped."""

from __future__ import annotations

import os
import time
from typing import overload

_PARALLEL_BRIDGE_READY_CAP_SEC = 180.0
_SIGNOFF_PARALLEL_BRIDGE_READY_CAP_SEC = 240.0
_SERIAL_BRIDGE_READY_CAP_SEC = 60.0
# A saturated host compiles single Turbopack chunks in ~190s (measured 2026-10-17 at 6-way
# parallel, load 64), so a fixed parallel cap killed pages that were still downloading scripts.
_BRIDGE_READY_CAP_LOAD_MAX = 3.0


def _bridge_ready_cap_scale() -> float:
    """How far a bridge cap may stretch on a loaded host (1.0 when the host is quiet).

    Reuses the same load-per-core notion as the stale-UI probe budget so one busy host raises
    both thresholds instead of one of them silently aborting a healthy frontend.
    """
    from dev_gate.contract import HOST_LOAD_UPGRADE_RATIO, host_load_ratio

    ratio = host_load_ratio()
    if ratio <= HOST_LOAD_UPGRADE_RATIO:
        return 1.0
    span = (ratio - HOST_LOAD_UPGRADE_RATIO) / (
        _BRIDGE_READY_CAP_LOAD_MAX - HOST_LOAD_UPGRADE_RATIO
    )
    return 1.0 + min(1.0, span)


def _parallel_bridge_ready_cap_sec() -> float:
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return _SIGNOFF_PARALLEL_BRIDGE_READY_CAP_SEC
    return _PARALLEL_BRIDGE_READY_CAP_SEC * _bridge_ready_cap_scale()


def _serial_bridge_ready_cap_sec() -> float:
    """Serial lane cap for one page's bridge wait.

    The serial lane had a fixed 60s ceiling while the parallel lane already scaled with the host load:
    a cold client bundle needs the dev server to compile it (a single chunk was measured at ~190s on a
    saturated host), so the fixed ceiling aborted exactly the pages that needed the most time.
    """
    return _SERIAL_BRIDGE_READY_CAP_SEC * _bridge_ready_cap_scale()


def _resolve_bridge_ready_timeout_sec(timeout_sec: float) -> float:
    """Parallel SHPOIB hydrate queue can defer React mount beyond 60s."""
    from dev_gate.contract import shared_ui_hydrate_wait_sec

    from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

    if not parallel_shared_ui_hydrate_queue_enabled():
        return min(_serial_bridge_ready_cap_sec(), timeout_sec)
    # The bridge-level wait must never undercut the per-page cap it wraps: a fixed 180s constant here
    # would clamp a loaded host straight back down. The admission wall stays the outer bound.
    parallel_cap = min(
        _parallel_bridge_ready_cap_sec(), float(shared_ui_hydrate_wait_sec())
    )
    return min(float(shared_ui_hydrate_wait_sec()), max(parallel_cap, timeout_sec))


def _bootstrap_hot_path_reused() -> bool:
    return os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "reused"


def _bootstrap_hot_path_fast() -> bool:
    if _bootstrap_hot_path_reused():
        return True
    return (
        os.environ.get("MYRM_E2E_PHASE_C_BURST_SKIP_ATTACH", "").strip() == "1"
        and os.environ.get("MYRM_E2E_BOOTSTRAP_HOT_PATH", "").strip() == "fast_create"
    )


def _shared_ui_deadline_extend_cap_sec() -> float:
    """Scale shared UI contract extension under parallel mux pressure (v2.2)."""
    base = 90.0
    try:
        from dev_gate.contract.parallel_pressure import parallel_chrome_e2e_pressure

        peers = parallel_chrome_e2e_pressure()
        if peers >= 2:
            return min(180.0, base + peers * 15.0)
    except ImportError:
        pass
    return base


@overload
def _extend_shared_ui_deadline_if_wall_allows(deadline: float) -> float: ...


@overload
def _extend_shared_ui_deadline_if_wall_allows(deadline: None) -> None: ...


def _extend_shared_ui_deadline_if_wall_allows(
    deadline: float | None,
) -> float | None:
    """Extend an expired inner deadline when outer bootstrap/body wall still has budget."""
    if deadline is None or time.monotonic() < deadline:
        return deadline
    from e2e_session_runtime.lifecycle import current_phase, remaining_wall_sec

    remaining = remaining_wall_sec()
    extend_floor = 20.0 if os.environ.get("E2E_SIGNOFF", "").strip() == "1" else 45.0
    phase = current_phase()
    if phase not in {"bootstrap", "body"} or remaining <= extend_floor:
        return deadline
    extend_cap = _shared_ui_deadline_extend_cap_sec()
    return time.monotonic() + min(extend_cap, remaining - 10.0)
