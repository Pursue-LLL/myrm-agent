"""E2EOrchestrator — Dev Gate E2E session SSOT (R65-B over R62 lifecycle).

[INPUT]
- e2e_session_lifecycle.py (phase budgets)
- transport_supervisor.py (recovery budget)

[OUTPUT]
- orchestrator_snapshot(), export_session_env(), begin_body_wall_budget(), ...

[POS]
Single import path for E2E session orchestration; replaces e2e_wall_budget facade.
"""

from __future__ import annotations

from typing import Literal

from e2e_session_lifecycle import (
    ENV_PROGRESS_AT,
    ENV_WALL_PHASE,
    ENV_WALL_STARTED,
    SessionPhase,
    assert_phase_budget,
    begin_body_wall_budget,
    begin_bootstrap_phase,
    begin_teardown_phase,
    budgets_remaining,
    current_phase,
    export_session_env,
    phase_cap_sec,
    provider_readiness_gate_sync,
    remaining_wall_sec,
    resolve_budget_policy,
    resolve_lifecycle_profile,
    stream_wait_cap_sec,
    touch_wall_progress,
    transition_to_phase,
    wall_started_monotonic,
)
from transport_supervisor import recovery_budget_remaining

AdmissionToken = Literal[
    "shpoib_slot",
    "mux_session",
    "cold_attach",
    "stream_lock",
]

__all__ = [
    "AdmissionToken",
    "ENV_PROGRESS_AT",
    "ENV_WALL_PHASE",
    "ENV_WALL_STARTED",
    "SessionPhase",
    "assert_phase_budget",
    "assert_wall_budget",
    "begin_body_wall_budget",
    "begin_bootstrap_phase",
    "begin_teardown_phase",
    "budgets_remaining",
    "current_phase",
    "export_session_env",
    "export_wall_budget_env",
    "holder_exceeded_wall_budget",
    "holder_progress_stale",
    "orchestrator_snapshot",
    "phase_cap_sec",
    "provider_readiness_gate_sync",
    "remaining_wall_sec",
    "resolve_budget_policy",
    "resolve_lifecycle_profile",
    "stream_wait_cap_sec",
    "touch_wall_progress",
    "transition_to_phase",
    "wall_started_monotonic",
]


def export_wall_budget_env() -> dict[str, str]:
    return export_session_env(phase="admit")


def assert_wall_budget(phase_label: str) -> None:
    assert_phase_budget(phase_label)


def holder_exceeded_wall_budget(holder_elapsed_sec: int) -> bool:
    from dev_gate_contract import LIVE_SINGLE_TEST_WALL_CLOCK_SEC

    return int(holder_elapsed_sec) >= int(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)


def holder_progress_stale(holder_progress_at: float | None) -> bool:
    import time

    from dev_gate_contract import STALL_PROGRESS_SEC

    if holder_progress_at is None:
        return True
    return (time.monotonic() - holder_progress_at) >= float(STALL_PROGRESS_SEC)


def orchestrator_snapshot() -> dict[str, object]:
    lifecycle = budgets_remaining()
    lifecycle["mux_recovery_remaining_sec"] = recovery_budget_remaining()
    return lifecycle
