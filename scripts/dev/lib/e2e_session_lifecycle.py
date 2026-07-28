"""E2E Session Lifecycle SSOT (R62 four-phase model).

[INPUT]
- dev_gate_contract.py (phase budget constants, is_e2e_signoff_runtime)

[OUTPUT]
- BudgetPolicy, SessionPhase, transition_to_phase(), begin_body_wall_budget()
- assert_phase_budget(), budgets_remaining(), provider_readiness_gate_sync()

[POS]
Dev Gate layer — unified ADMIT → BOOTSTRAP → BODY → TEARDOWN lifecycle.
BODY budget: dev LIVE_AGENT 600s (R96-R62); READ and signoff 600s. Queue/bootstrap never consume BODY budget.
"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from typing import Final, Literal

from dev_gate_contract import (
    E2E_ADMISSION_WALL_CLOCK_SEC,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF,
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
    E2E_TEARDOWN_WALL_CLOCK_SEC,
    LIVE_AGENT_BODY_WALL_CLOCK_SEC,
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    is_e2e_signoff_runtime,
)

SessionPhase = Literal["admit", "bootstrap", "body", "teardown"]
LifecycleProfile = Literal["dev", "signoff"]

ENV_WALL_STARTED: Final[str] = "MYRM_E2E_WALL_STARTED_MONOTONIC"
ENV_PROGRESS_AT: Final[str] = "MYRM_E2E_WALL_PROGRESS_AT_MONOTONIC"
ENV_WALL_PHASE: Final[str] = "MYRM_E2E_WALL_PHASE"

_LEGACY_PHASE_ALIASES: Final[dict[str, SessionPhase]] = {
    "admission": "admit",
    "signoff": "admit",
    "pytest_body": "body",
}


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    profile: LifecycleProfile
    admit_sec: int
    bootstrap_sec: int
    body_sec: int
    teardown_sec: int

    def cap_for(self, phase: SessionPhase) -> int:
        return {
            "admit": self.admit_sec,
            "bootstrap": self.bootstrap_sec,
            "body": self.body_sec,
            "teardown": self.teardown_sec,
        }[phase]

    def outer_kill_sec(self, *, pytest_safe_buffer_sec: int) -> int:
        return (
            self.admit_sec + self.bootstrap_sec + self.body_sec + pytest_safe_buffer_sec
        )


def resolve_lifecycle_profile() -> LifecycleProfile:
    return "signoff" if is_e2e_signoff_runtime() else "dev"


def resolve_budget_policy() -> BudgetPolicy:
    profile = resolve_lifecycle_profile()
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    body_sec = LIVE_SINGLE_TEST_WALL_CLOCK_SEC
    if profile == "dev" and lane == "LIVE_AGENT":
        body_sec = LIVE_AGENT_BODY_WALL_CLOCK_SEC
    if profile == "signoff":
        return BudgetPolicy(
            profile=profile,
            admit_sec=E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
            bootstrap_sec=E2E_BOOTSTRAP_WALL_CLOCK_SEC_SIGNOFF,
            body_sec=LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
            teardown_sec=E2E_TEARDOWN_WALL_CLOCK_SEC,
        )
    return BudgetPolicy(
        profile=profile,
        admit_sec=E2E_ADMISSION_WALL_CLOCK_SEC,
        bootstrap_sec=E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV,
        body_sec=body_sec,
        teardown_sec=E2E_TEARDOWN_WALL_CLOCK_SEC,
    )


def _normalize_phase(raw: str) -> SessionPhase:
    normalized = raw.strip().lower()
    if normalized in _LEGACY_PHASE_ALIASES:
        return _LEGACY_PHASE_ALIASES[normalized]
    if normalized in ("admit", "bootstrap", "body", "teardown"):
        return normalized  # type: ignore[return-value]
    return "admit"


def current_phase() -> SessionPhase:
    return _normalize_phase(os.environ.get(ENV_WALL_PHASE, "admit"))


def wall_started_monotonic() -> float | None:
    raw = os.environ.get(ENV_WALL_STARTED, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def touch_wall_progress(*, current_node: str | None = None) -> None:
    os.environ[ENV_PROGRESS_AT] = str(time.monotonic())
    try:
        from e2e_session_snapshot import touch_session_progress

        touch_session_progress(current_node=current_node)
    except ImportError:
        pass


def _read_progress_at_monotonic() -> float | None:
    raw = os.environ.get(ENV_PROGRESS_AT, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def assert_body_progress_not_stale(phase_label: str) -> None:
    """Fail-fast when BODY phase has no progress token refresh within STALL_PROGRESS_SEC."""
    if current_phase() != "body":
        return
    from dev_gate_contract import STALL_PROGRESS_SEC

    progress_at = _read_progress_at_monotonic()
    elapsed = elapsed_wall_sec()
    if progress_at is None:
        return
    stale = time.monotonic() - progress_at
    if elapsed >= 30.0 and stale >= float(STALL_PROGRESS_SEC):
        print(
            f"E2E_BODY_PROGRESS_STALL: stale={int(stale)}s "
            f"cap={STALL_PROGRESS_SEC}s elapsed={int(elapsed)}s "
            f"phase={phase_label} wall_phase=body",
            file=sys.stderr,
            flush=True,
        )
        raise TimeoutError(
            f"E2E_BODY_PROGRESS_STALL after {int(stale)}s without progress "
            f"(phase={phase_label})"
        )


def assert_phase_budget(phase_label: str) -> None:
    assert_body_progress_not_stale(phase_label)
    wall_cap = phase_cap_sec()
    elapsed = elapsed_wall_sec()
    phase = current_phase()
    if elapsed >= float(wall_cap):
        print(
            f"E2E_WALL_BUDGET_FAIL_FAST: elapsed={int(elapsed)}s "
            f"cap={wall_cap}s remaining=0s phase={phase_label} wall_phase={phase}",
            file=sys.stderr,
            flush=True,
        )
        raise TimeoutError(
            f"E2E_WALL_BUDGET_FAIL_FAST after {int(elapsed)}s "
            f"(phase={phase_label}, wall_phase={phase})"
        )
    touch_wall_progress(current_node=phase_label)


def elapsed_wall_sec() -> float:
    started = wall_started_monotonic()
    if started is None:
        return 0.0
    return max(0.0, time.monotonic() - started)


def phase_cap_sec(phase: SessionPhase | None = None) -> int:
    resolved = phase or current_phase()
    return resolve_budget_policy().cap_for(resolved)


def remaining_wall_sec() -> float:
    return max(0.0, float(phase_cap_sec()) - elapsed_wall_sec())


def transition_to_phase(phase: SessionPhase, *, label: str = "") -> None:
    started = time.monotonic()
    stamp = str(started)
    os.environ[ENV_WALL_STARTED] = stamp
    os.environ[ENV_PROGRESS_AT] = stamp
    os.environ[ENV_WALL_PHASE] = phase
    cap = phase_cap_sec(phase)
    note = f" label={label}" if label else ""
    print(
        f"E2E_SESSION_PHASE: phase={phase} cap={cap}s "
        f"profile={resolve_lifecycle_profile()}{note}",
        file=sys.stderr,
        flush=True,
    )


def export_session_env(*, phase: SessionPhase = "admit") -> dict[str, str]:
    started = time.monotonic()
    stamp = str(started)
    return {
        ENV_WALL_STARTED: stamp,
        ENV_PROGRESS_AT: stamp,
        ENV_WALL_PHASE: phase,
    }


def _reset_phase_mux_recovery_budget(*, phase_label: str) -> None:
    """Fresh mux recovery ledger per lifecycle phase (R73-F TPC M1)."""
    try:
        from transport_supervisor import reset_session_recovery_budget

        reset_session_recovery_budget()
        print(
            f"E2E_MUX_BUDGET_RESET: phase={phase_label}",
            file=sys.stderr,
            flush=True,
        )
    except ImportError:
        pass


def begin_bootstrap_phase(*, phase_label: str = "bootstrap") -> None:
    """Enter bootstrap phase with a fresh wall clock (even if body already started)."""
    transition_to_phase("bootstrap", label=phase_label)
    _reset_phase_mux_recovery_budget(phase_label=phase_label)


def complete_bootstrap_phase(*, phase_label: str = "pytest_body") -> None:
    """Re-enter body phase with a fresh wall clock after cdp bootstrap finishes."""
    begin_body_wall_budget(phase_label=phase_label)


def begin_body_wall_budget(*, phase_label: str = "pytest_body") -> None:
    transition_to_phase("body", label=phase_label)
    _reset_phase_mux_recovery_budget(phase_label=phase_label)
    print(
        f"E2E_WALL_BUDGET_BODY_START: cap={phase_cap_sec('body')}s phase={phase_label}",
        file=sys.stderr,
        flush=True,
    )


def begin_teardown_phase(*, phase_label: str = "teardown") -> None:
    transition_to_phase("teardown", label=phase_label)


def stream_wait_cap_sec(configured_wait: int) -> int:
    cap = phase_cap_sec()
    if wall_started_monotonic() is None:
        return min(max(0, int(configured_wait)), cap)
    remaining = int(remaining_wall_sec())
    if remaining <= 0:
        return 0
    return min(max(0, int(configured_wait)), remaining)


def budgets_remaining() -> dict[str, object]:
    policy = resolve_budget_policy()
    phase = current_phase()
    return {
        "profile": policy.profile,
        "phase": phase,
        "remaining_sec": remaining_wall_sec(),
        "budgets_remaining": {
            "admit_sec": policy.admit_sec,
            "bootstrap_sec": policy.bootstrap_sec,
            "body_sec": policy.body_sec,
            "teardown_sec": policy.teardown_sec,
        },
    }


def provider_readiness_gate_sync() -> None:
    """Fail-closed provider readiness gate for BOOTSTRAP phase."""
    from cdp_chat_support import (  # noqa: PLC0415
        fetch_provider_readiness_snapshot,
        wait_e2e_provider_ready,
    )

    bootstrap_cap = float(phase_cap_sec("bootstrap"))
    wait_budget = max(5.0, min(60.0, bootstrap_cap))
    if wait_e2e_provider_ready(timeout_sec=wait_budget):
        return
    snapshot = fetch_provider_readiness_snapshot()
    raise RuntimeError(
        "E2E_PROVIDER_READINESS_GATE_FAIL: "
        f"provider not ready within {int(wait_budget)}s: {snapshot}"
    )
