"""E2E Session Lifecycle SSOT (R62 four-phase model).

[INPUT]
- dev_gate/contract.py (phase budget constants, is_e2e_signoff_runtime)

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

from dev_gate.contract import (
    E2E_ADMISSION_WALL_CLOCK_SEC,
    E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV,
    E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
    E2E_TEARDOWN_WALL_CLOCK_SEC,
    LIVE_AGENT_BODY_WALL_CLOCK_SEC,
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    is_e2e_signoff_runtime,
)

SessionPhase = Literal["admit", "bootstrap", "body", "teardown"]
LifecycleProfile = Literal["dev", "signoff"]

ENV_WALL_STARTED: Final[str] = "MYRM_E2E_WALL_STARTED_MONOTONIC"
ENV_MONO_STARTED: Final[str] = "MYRM_E2E_MONO_STARTED_MONOTONIC"
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


def _private_shpoib_bootstrap_lane(lane: str) -> bool:
    """R220: NAMESPACE_WRITE → RESOURCE_WRITE lease still runs SHPOIB private backend."""
    from dev_gate.contract import private_shpoib_runtime_active

    if not private_shpoib_runtime_active():
        return False
    return lane in {"LIVE_AGENT", "RESOURCE_WRITE"}


def resolve_budget_policy() -> BudgetPolicy:
    profile = resolve_lifecycle_profile()
    if profile == "signoff":
        from dev_gate.contract import signoff_effective_bootstrap_wall_sec

        return BudgetPolicy(
            profile=profile,
            admit_sec=E2E_SIGNOFF_ADMIT_WALL_CLOCK_SEC,
            bootstrap_sec=int(signoff_effective_bootstrap_wall_sec()),
            body_sec=LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
            teardown_sec=E2E_TEARDOWN_WALL_CLOCK_SEC,
        )
    return BudgetPolicy(
        profile=profile,
        admit_sec=E2E_ADMISSION_WALL_CLOCK_SEC,
        bootstrap_sec=E2E_BOOTSTRAP_WALL_CLOCK_SEC_DEV,
        body_sec=LIVE_AGENT_BODY_WALL_CLOCK_SEC,
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


def mono_started_monotonic() -> float | None:
    raw = os.environ.get(ENV_MONO_STARTED, "").strip()
    if not raw:
        return wall_started_monotonic()
    try:
        return float(raw)
    except ValueError:
        return None


def _ensure_mono_started() -> float:
    existing = mono_started_monotonic()
    if existing is not None:
        return existing
    now = time.monotonic()
    stamp = str(now)
    os.environ[ENV_MONO_STARTED] = stamp
    if wall_started_monotonic() is None:
        os.environ[ENV_WALL_STARTED] = stamp
        os.environ[ENV_PROGRESS_AT] = stamp
    return now


def _cumulative_phase_cap_sec(phase: SessionPhase) -> int:
    policy = resolve_budget_policy()
    if phase == "admit":
        return policy.admit_sec
    if phase == "bootstrap":
        return policy.admit_sec + policy.bootstrap_sec
    if phase == "body":
        return policy.admit_sec + policy.bootstrap_sec + policy.body_sec
    return (
        policy.admit_sec + policy.bootstrap_sec + policy.body_sec + policy.teardown_sec
    )


def touch_wall_progress(*, current_node: str | None = None) -> None:
    os.environ[ENV_PROGRESS_AT] = str(time.monotonic())
    try:
        from e2e_session_runtime.snapshot import touch_session_progress

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
    from dev_gate.contract import shpoib_parallel_stall_progress_sec

    stall_cap = shpoib_parallel_stall_progress_sec()
    progress_at = _read_progress_at_monotonic()
    elapsed = elapsed_wall_sec()
    if progress_at is None:
        return
    stale = time.monotonic() - progress_at
    if elapsed >= 30.0 and stale >= stall_cap:
        print(
            f"E2E_BODY_PROGRESS_STALL: stale={int(stale)}s "
            f"cap={int(stall_cap)}s elapsed={int(elapsed)}s "
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
    if phase_label == "E2E_SHARED_STACK_RECOVERY_WAIT":
        try:
            from dev_gate.contract import (
                is_e2e_signoff_runtime,
                signoff_stack_recovery_admit_budget_sec,
            )

            if is_e2e_signoff_runtime():
                wall_cap = max(
                    wall_cap,
                    signoff_stack_recovery_admit_budget_sec(),
                )
        except ImportError:
            pass
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
    started = mono_started_monotonic()
    if started is None:
        return 0.0
    return max(0.0, time.monotonic() - started)


def phase_cap_sec(phase: SessionPhase | None = None) -> int:
    resolved = phase or current_phase()
    return _cumulative_phase_cap_sec(resolved)


def remaining_wall_sec() -> float:
    return max(
        0.0, float(_cumulative_phase_cap_sec(current_phase())) - elapsed_wall_sec()
    )


def transition_to_phase(phase: SessionPhase, *, label: str = "") -> None:
    _ensure_mono_started()
    if wall_started_monotonic() is None:
        stamp = str(time.monotonic())
        os.environ[ENV_WALL_STARTED] = stamp
        os.environ[ENV_PROGRESS_AT] = stamp
    else:
        touch_wall_progress(current_node=label or phase)
    os.environ[ENV_WALL_PHASE] = phase
    cap = _cumulative_phase_cap_sec(phase)
    note = f" label={label}" if label else ""
    print(
        f"E2E_SESSION_PHASE: phase={phase} cap={cap}s "
        f"mono_elapsed={int(elapsed_wall_sec())}s "
        f"profile={resolve_lifecycle_profile()}{note}",
        file=sys.stderr,
        flush=True,
    )


def export_session_env(*, phase: SessionPhase = "admit") -> dict[str, str]:
    started = time.monotonic()
    stamp = str(started)
    return {
        ENV_MONO_STARTED: stamp,
        ENV_WALL_STARTED: stamp,
        ENV_PROGRESS_AT: stamp,
        ENV_WALL_PHASE: phase,
    }


def begin_bootstrap_phase(*, phase_label: str = "bootstrap") -> None:
    """Enter bootstrap phase with a fresh wall clock (even if body already started).

    R215: when BODY is already active (mux heal CDP re-bootstrap), keep BODY wall
    budget — do not downgrade to bootstrap cap.
    """
    if current_phase() == "body":
        _begin_body_cdp_rebootstrap(phase_label=phase_label)
        return
    transition_to_phase("bootstrap", label=phase_label)


def _begin_body_cdp_rebootstrap(*, phase_label: str) -> None:
    touch_wall_progress(current_node=phase_label)
    print(
        f"E2E_BODY_CDP_REBOOTSTRAP: phase={phase_label} "
        f"body_remaining={int(remaining_wall_sec())}s",
        file=sys.stderr,
        flush=True,
    )


def complete_bootstrap_phase(*, phase_label: str = "pytest_body") -> None:
    """Re-enter body phase with a fresh wall clock after cdp bootstrap finishes."""
    if current_phase() == "body":
        touch_wall_progress(current_node=phase_label)
        try:
            from e2e_session_runtime.snapshot import touch_session_progress

            touch_session_progress()
        except ImportError:
            pass
        print(
            f"E2E_BODY_CDP_REBOOTSTRAP_DONE: phase={phase_label} "
            f"body_remaining={int(remaining_wall_sec())}s",
            file=sys.stderr,
            flush=True,
        )
        return
    print(
        f"E2E_PAGE_OPEN_SEAL: phase={phase_label}",
        file=sys.stderr,
        flush=True,
    )
    begin_body_wall_budget(phase_label=phase_label)
    _transition_dev_gate_to_body(current_node=phase_label)


def _transition_dev_gate_to_body(*, current_node: str) -> None:
    """Seal coordinator PAGE_OPEN→BODY and emit the product SLO measurement."""
    session_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    owner_token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
    if not session_id or not owner_token:
        return
    from dev_gate.cli import send

    response = send({"operation": "snapshot", "session_id": session_id})
    session = response.get("session") if isinstance(response, dict) else None
    if not isinstance(session, dict):
        raise TypeError(f"E2E_DEV_GATE_BODY_TRANSITION: session missing {session_id}")
    state = str(session.get("state", ""))
    if state == "PREPARING":
        response = send(
            {
                "operation": "transition",
                "session_id": session_id,
                "owner_token": owner_token,
                "target": "PAGE_OPEN",
                "current_node": "E2E_PYTEST_SUBPROCESS",
            }
        )
        session = response.get("session") if isinstance(response, dict) else None
        state = str(session.get("state", "")) if isinstance(session, dict) else ""
    if state == "PAGE_OPEN":
        # Re-snapshot before BODY: parallel open_mcp_page / post_cdp_bootstrap may
        # have sealed BODY while local wall phase is still bootstrap.
        response = send({"operation": "snapshot", "session_id": session_id})
        session = response.get("session") if isinstance(response, dict) else None
        state = str(session.get("state", "")) if isinstance(session, dict) else ""
        if state == "PAGE_OPEN":
            try:
                response = send(
                    {
                        "operation": "transition",
                        "session_id": session_id,
                        "owner_token": owner_token,
                        "target": "BODY",
                        "current_node": current_node,
                    }
                )
            except RuntimeError as exc:
                # TOCTOU: a concurrent complete_bootstrap_phase (pytest fixture +
                # post_cdp_bootstrap) may seal BODY between re-snapshot and this
                # transition. Treat an already-sealed BODY as success.
                if "BODY->BODY" not in str(exc):
                    raise
                response = send({"operation": "snapshot", "session_id": session_id})
            session = response.get("session") if isinstance(response, dict) else None
            state = str(session.get("state", "")) if isinstance(session, dict) else ""
    if state != "BODY" or not isinstance(session, dict):
        raise RuntimeError(
            f"E2E_DEV_GATE_BODY_TRANSITION: expected BODY, got {state or 'UNKNOWN'}"
        )
    submitted_at = session.get("submitted_at")
    phase_started_at = session.get("phase_started_at")
    if not isinstance(submitted_at, (int, float)) or not isinstance(
        phase_started_at, (int, float)
    ):
        raise TypeError("E2E_DEV_GATE_BODY_TRANSITION: timestamps unavailable")
    admit_to_body = max(0.0, float(phase_started_at) - float(submitted_at))
    print(
        f"E2E_DEV_GATE_BODY_START: admit_to_body_sec={admit_to_body:.3f} "
        f"session={session_id} node={current_node}",
        file=sys.stderr,
        flush=True,
    )


def begin_body_wall_budget(*, phase_label: str = "pytest_body") -> None:
    transition_to_phase("body", label=phase_label)
    try:
        from e2e_session_runtime.snapshot import touch_session_progress

        touch_session_progress()
    except ImportError:
        pass
    print(
        f"E2E_WALL_BUDGET_BODY_START: cap={phase_cap_sec('body')}s "
        f"mono_elapsed={int(elapsed_wall_sec())}s phase={phase_label}",
        file=sys.stderr,
        flush=True,
    )


def seal_page_open_body_budget(*, phase_label: str = "page_open_seal") -> None:
    """PageOpenSeal — start BODY wall only after owned page is ready (Phase3-B)."""
    print(
        f"E2E_PAGE_OPEN_SEAL: phase={phase_label}",
        file=sys.stderr,
        flush=True,
    )
    begin_body_wall_budget(phase_label=phase_label)


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
    from cdp_chat.support import (
        fetch_provider_readiness_snapshot,
        wait_e2e_provider_ready,
    )
    from dev_gate.contract import (
        PROVIDER_READINESS_GATE_BASE_SEC,
        provider_readiness_gate_effective_budget_sec,
        provider_readiness_gate_wait_sec,
    )

    bootstrap_cap = float(phase_cap_sec("bootstrap"))
    scaled_wait = provider_readiness_gate_wait_sec()
    wait_budget = provider_readiness_gate_effective_budget_sec(
        phase=current_phase(),
        remaining_wall_sec=remaining_wall_sec(),
        bootstrap_cap=bootstrap_cap,
    )
    if scaled_wait > PROVIDER_READINESS_GATE_BASE_SEC:
        print(
            f"E2E_PROVIDER_READINESS_GATE_WAIT: budget={wait_budget:.0f}s "
            f"parallel_scaled={scaled_wait:.0f}s",
            file=sys.stderr,
            flush=True,
        )
    if wait_e2e_provider_ready(timeout_sec=wait_budget):
        return
    snapshot = fetch_provider_readiness_snapshot()
    provider = snapshot.get("provider")
    if isinstance(provider, dict) and bool(provider.get("is_ready")):
        return
    raise RuntimeError(
        "E2E_PROVIDER_READINESS_GATE_FAIL: "
        f"provider not ready within {int(wait_budget)}s: {snapshot}"
    )
