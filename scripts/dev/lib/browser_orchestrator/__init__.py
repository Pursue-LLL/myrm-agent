"""Browser Orchestrator package — public re-exports from core."""

from browser_orchestrator import core as _core

from browser_orchestrator.core import (
    MAX_OPERATION_CREDITS,
    OPERATION_QUEUE_SLO_SEC,
    BrowserPlaneHealth,
    assert_browser_orchestrator_daemon_ready,
    browser_operation_credit_slot,
    browser_orchestrator_snapshot,
    estimate_operation_wait_sec,
    orchestrator_queue_observability,
    prune_self_owned_blanks,
    wait_for_operation_credit,
)

# Private probes remain visible on the facade for diagnostics and deterministic
# tests; core.browser_orchestrator_snapshot reads facade overrides when present.
_try_daemon_snapshot = _core._try_daemon_snapshot
_mux_scheduler_probe = _core._mux_scheduler_probe
_effective_operation_credit_cap = _core._effective_operation_credit_cap

__all__ = [
    "MAX_OPERATION_CREDITS",
    "OPERATION_QUEUE_SLO_SEC",
    "BrowserPlaneHealth",
    "assert_browser_orchestrator_daemon_ready",
    "browser_operation_credit_slot",
    "browser_orchestrator_snapshot",
    "estimate_operation_wait_sec",
    "orchestrator_queue_observability",
    "prune_self_owned_blanks",
    "wait_for_operation_credit",
]
