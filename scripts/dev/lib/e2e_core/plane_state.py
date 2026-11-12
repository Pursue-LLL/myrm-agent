"""Plane health state model: the states, receipts and snapshot, and the pure rules that classify a plane.

[INPUT]
- Counts and health strings handed in by the caller (POS: no I/O of its own)

[OUTPUT]
- `PlaneHealthState` / `PlaneHealthSnapshot` / `ReapReceipt` / `ConvergeReceipt`: the data the plane health facade returns
- `classify_state()` / `build_agent_rule()`: map observations to a state and to the one-line rule an agent follows

[POS]
Dev Gate infra layer. Leaf module of `plane_health.py`; it probes nothing and mutates nothing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PlaneHealthState(str, Enum):
    OBSERVABLE = "OBSERVABLE"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FAILED_LATCHED = "FAILED_LATCHED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReapReceipt:
    mux_pid_removed: bool
    mux_socket_removed: bool
    orchestrator_recycled: bool
    detail: str


@dataclass(frozen=True)
class ConvergeReceipt:
    ok: bool
    action: str
    detail: str
    elapsed_sec: float


@dataclass(frozen=True)
class PlaneHealthSnapshot:
    state: PlaneHealthState
    mux_daemon_count: int
    orchestrator_state: str
    orchestrator_health: str
    mux_snapshot_available: bool
    epoch_match: bool
    drift_pending: bool
    wave_leases: int
    cluster_active: int
    agent_rule: str
    converge_action: str | None


def classify_state(
    *,
    mux_count: int,
    orch_health: str,
    orch_state: str,
    mux_available: bool,
    orchestrator_listening: bool = True,
) -> PlaneHealthState:
    if orch_state == "RECOVERING" or orch_health == "RECOVERING":
        return PlaneHealthState.RECOVERING
    if orch_state == "FAILED" or orch_health == "FAILED":
        return PlaneHealthState.FAILED_LATCHED
    # A live mux with a lapsed orchestrator snapshot is UNKNOWN, not STALE. The
    # snapshot is unavailable whenever the orchestrator RPC did not answer in time, and
    # under parallel load that RPC legitimately queues behind peer tabs — the same
    # reason chrome-e2e-preflight::_heal_mux_under_parallel_attach_load trusts
    # upstream+ws+pid and skips its expensive probe. Classifying that transient
    # timeout as STALE failed every attach while the plane was actually healthy
    # (observed: 3/4 SHARED lanes failed body_started=0 under a 4-lane ramp).
    if mux_count < 1:
        return PlaneHealthState.STALE
    if not mux_available:
        # `mux_snapshot_available` reports whether the orchestrator-daemon status RPC
        # answered, not whether the plane is down (core._try_daemon_snapshot returns
        # None on any RPC miss). A listening daemon means the plane is alive and the
        # snapshot merely lapsed under load -> recoverable, not STALE.
        return (
            PlaneHealthState.UNKNOWN
            if orchestrator_listening
            else PlaneHealthState.STALE
        )
    if orch_health in {"DEGRADED", "UNKNOWN"}:
        return PlaneHealthState.DEGRADED
    if orch_health == "READY" and mux_count >= 1 and mux_available:
        return PlaneHealthState.OBSERVABLE
    return PlaneHealthState.UNKNOWN


def build_agent_rule(
    state: PlaneHealthState,
    *,
    epoch_match: bool,
    drift_pending: bool,
    wave_leases: int,
) -> str:
    if state is PlaneHealthState.OBSERVABLE and epoch_match:
        return "READY: cluster ready for chrome_e2e launch"
    if state is PlaneHealthState.OBSERVABLE:
        return (
            "PLANE_OBSERVABLE: mux/orchestrator healthy — read epoch_match from "
            "e2e-context for SHARED launch routing"
        )
    if not epoch_match and drift_pending and wave_leases == 0:
        return (
            "DRIFT_PENDING: wave idle — run ./myrm-dev restart --chrome to apply workspace "
            "epoch, or declare PRIVATE for workspace backend code; do not stop other pytest"
        )
    if state in {PlaneHealthState.STALE, PlaneHealthState.FAILED_LATCHED}:
        if wave_leases == 0:
            return (
                "PLANE_STALE: mux/orchestrator unhealthy — run ./myrm-dev restart --chrome "
                "or wait for plane converge; verify-api does not heal mux/orch; "
                "do not stop other pytest"
            )
        return (
            "PLANE_DEGRADED: parallel active — plane heal deferred until wave idle; "
            "do not stop other pytest"
        )
    if state is PlaneHealthState.RECOVERING:
        return "PLANE_RECOVERING: wait for orchestrator recovery or retry attach"
    if state is PlaneHealthState.UNKNOWN:
        return (
            "PLANE_UNKNOWN: orchestrator snapshot unavailable while mux is alive — "
            "transient under parallel load; launch proceeds and attach retries. "
            "If it persists with no active tests, run ./myrm-dev e2e-context json then "
            "./myrm-dev restart --chrome"
        )
    return "PLANE_UNKNOWN: run ./myrm-dev e2e-context json and execute agent_rule"
