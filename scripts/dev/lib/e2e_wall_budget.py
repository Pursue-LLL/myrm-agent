"""Monotonic wall-clock budget for Chrome E2E sessions (R39 + R58 dual-phase).

[INPUT]
- dev_gate_contract.py (LIVE_SINGLE_TEST_WALL_CLOCK_SEC, E2E_ADMISSION_WALL_CLOCK_SEC)

[OUTPUT]
- export_wall_budget_env(), begin_body_wall_budget(), assert_wall_budget()
- stream_wait_cap_sec(), holder_exceeded_wall_budget()

[POS]
SSOT for admission queue (≤900s) vs pytest body (≤600s) wall clocks.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Final, Literal

from dev_gate_contract import (
    E2E_ADMISSION_WALL_CLOCK_SEC,
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    STALL_PROGRESS_SEC,
)

ENV_WALL_STARTED: Final[str] = "MYRM_E2E_WALL_STARTED_MONOTONIC"
ENV_PROGRESS_AT: Final[str] = "MYRM_E2E_WALL_PROGRESS_AT_MONOTONIC"
ENV_WALL_PHASE: Final[str] = "MYRM_E2E_WALL_PHASE"

WallPhase = Literal["admission", "body"]


def _wall_phase() -> WallPhase:
    raw = os.environ.get(ENV_WALL_PHASE, "admission").strip().lower()
    if raw == "body":
        return "body"
    return "admission"


def _body_wall_cap_sec() -> int:
    signoff = os.environ.get("E2E_SIGNOFF", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    if signoff:
        raw = os.environ.get("MYRM_E2E_BODY_WALL_SEC", "900").strip()
        try:
            return max(600, int(raw))
        except ValueError:
            return 900
    return int(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)


def _active_wall_cap_sec() -> int:
    if _wall_phase() == "body":
        return _body_wall_cap_sec()
    return int(E2E_ADMISSION_WALL_CLOCK_SEC)


def export_wall_budget_env() -> dict[str, str]:
    """Return env vars to export at chrome_e2e session start (admission phase)."""
    started = time.monotonic()
    stamp = str(started)
    return {
        ENV_WALL_STARTED: stamp,
        ENV_PROGRESS_AT: stamp,
        ENV_WALL_PHASE: "admission",
    }


def begin_body_wall_budget(*, phase_label: str = "pytest_body") -> None:
    """Reset monotonic wall clock when admission completes and pytest body begins."""
    started = time.monotonic()
    stamp = str(started)
    os.environ[ENV_WALL_STARTED] = stamp
    os.environ[ENV_PROGRESS_AT] = stamp
    os.environ[ENV_WALL_PHASE] = "body"
    print(
        f"E2E_WALL_BUDGET_BODY_START: cap={_body_wall_cap_sec()}s "
        f"phase={phase_label}",
        file=sys.stderr,
        flush=True,
    )


def wall_started_monotonic() -> float | None:
    raw = os.environ.get(ENV_WALL_STARTED, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def touch_wall_progress() -> None:
    os.environ[ENV_PROGRESS_AT] = str(time.monotonic())


def progress_stale_sec() -> float:
    raw = os.environ.get(ENV_PROGRESS_AT, "").strip()
    if not raw:
        return 0.0
    try:
        last = float(raw)
    except ValueError:
        return 0.0
    return max(0.0, time.monotonic() - last)


def elapsed_wall_sec() -> float:
    started = wall_started_monotonic()
    if started is None:
        return 0.0
    return max(0.0, time.monotonic() - started)


def remaining_wall_sec() -> float:
    return max(0.0, float(_active_wall_cap_sec()) - elapsed_wall_sec())


def stream_wait_cap_sec(configured_wait: int) -> int:
    """Cap stream-lock wait by remaining monotonic wall budget for the active phase."""
    cap = _active_wall_cap_sec()
    if wall_started_monotonic() is None:
        return min(max(0, int(configured_wait)), cap)
    remaining = int(remaining_wall_sec())
    if remaining <= 0:
        return 0
    return min(max(0, int(configured_wait)), remaining)


def assert_wall_budget(phase: str) -> None:
    wall_cap = _active_wall_cap_sec()
    elapsed = elapsed_wall_sec()
    if elapsed >= float(wall_cap):
        print(
            f"E2E_WALL_BUDGET_FAIL_FAST: elapsed={int(elapsed)}s "
            f"cap={wall_cap}s "
            f"remaining=0s phase={phase} wall_phase={_wall_phase()}",
            file=sys.stderr,
            flush=True,
        )
        raise TimeoutError(
            f"E2E_WALL_BUDGET_FAIL_FAST after {int(elapsed)}s "
            f"(phase={phase}, wall_phase={_wall_phase()})"
        )
    touch_wall_progress()


def holder_exceeded_wall_budget(holder_elapsed_sec: int) -> bool:
    return int(holder_elapsed_sec) >= int(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)


def holder_progress_stale(holder_progress_at: float | None) -> bool:
    if holder_progress_at is None:
        return True
    return (time.monotonic() - holder_progress_at) >= float(STALL_PROGRESS_SEC)
