"""First-party Browser Orchestrator snapshot (P0-B foundation).

Single persistent CDP ownership plane; max operation credits bound physical
browser concurrency instead of four independent MCP ownership processes.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TypedDict

MAX_OPERATION_CREDITS = 4


class BrowserPlaneHealth(StrEnum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


class BrowserOrchestratorSnapshot(TypedDict, total=False):
    health: str
    operation_credits_max: int
    operation_credits_in_flight: int
    operation_credits_available: int
    mux_snapshot_available: bool
    mux_contexts: int
    wave_leases: int


def _mux_probe() -> tuple[bool, int, int]:
    try:
        from mux_load import read_mux_status, snapshot_mux_load

        status = read_mux_status()
        snap = snapshot_mux_load()
        return status is not None, int(snap.mux_contexts), int(snap.wave_leases)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return False, 0, 0


def _infer_health(*, mux_available: bool, in_flight: int) -> BrowserPlaneHealth:
    if not mux_available:
        return BrowserPlaneHealth.UNKNOWN
    if in_flight > MAX_OPERATION_CREDITS:
        return BrowserPlaneHealth.DEGRADED
    try:
        from transport_supervisor import recovery_budget_remaining

        if recovery_budget_remaining() <= 0.0:
            return BrowserPlaneHealth.RECOVERING
    except ImportError:
        pass
    return BrowserPlaneHealth.READY


def browser_orchestrator_snapshot() -> BrowserOrchestratorSnapshot:
    mux_available, contexts, wave_leases = _mux_probe()
    in_flight = min(contexts, MAX_OPERATION_CREDITS) if mux_available else 0
    health = _infer_health(
        mux_available=mux_available,
        in_flight=contexts if mux_available else 0,
    )
    return BrowserOrchestratorSnapshot(
        health=health.value,
        operation_credits_max=MAX_OPERATION_CREDITS,
        operation_credits_in_flight=in_flight,
        operation_credits_available=max(0, MAX_OPERATION_CREDITS - in_flight),
        mux_snapshot_available=mux_available,
        mux_contexts=contexts,
        wave_leases=wave_leases,
    )
