"""Monotonic wall-clock budget for Chrome E2E sessions (R39 Wall Budget Plane).

[INPUT]
- dev_gate_contract.py (LIVE_SINGLE_TEST_WALL_CLOCK_SEC, STALL_PROGRESS_SEC)

[OUTPUT]
- export_wall_budget_env(), assert_wall_budget(), stream_wait_cap_sec()
- holder_exceeded_wall_budget(), holder_progress_stale()

[POS]
SSOT for single-test 600s wall clock across test.sh bootstrap, stream queue, and pytest body.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Final

from dev_gate_contract import (
    LIVE_SINGLE_TEST_WALL_CLOCK_SEC,
    STALL_PROGRESS_SEC,
)

ENV_WALL_STARTED: Final[str] = "MYRM_E2E_WALL_STARTED_MONOTONIC"
ENV_PROGRESS_AT: Final[str] = "MYRM_E2E_WALL_PROGRESS_AT_MONOTONIC"


def export_wall_budget_env() -> dict[str, str]:
    """Return env vars to export at chrome_e2e session start."""
    started = time.monotonic()
    stamp = str(started)
    return {
        ENV_WALL_STARTED: stamp,
        ENV_PROGRESS_AT: stamp,
    }


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
    return max(0.0, float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC) - elapsed_wall_sec())


def stream_wait_cap_sec(configured_wait: int) -> int:
    """Cap stream-lock wait by remaining monotonic wall budget.

    Before ``export_wall_budget_env`` runs (stream/lease queue phase), the full
    configured wait is allowed so FIFO queue time does not consume pytest body budget.
    """
    if wall_started_monotonic() is None:
        return max(0, int(configured_wait))
    remaining = int(remaining_wall_sec())
    if remaining <= 0:
        return 0
    return min(max(0, int(configured_wait)), remaining)


def assert_wall_budget(phase: str) -> None:
    elapsed = elapsed_wall_sec()
    if elapsed >= float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC):
        print(
            f"E2E_WALL_BUDGET_FAIL_FAST: elapsed={int(elapsed)}s "
            f"cap={LIVE_SINGLE_TEST_WALL_CLOCK_SEC}s "
            f"remaining=0s phase={phase}",
            file=sys.stderr,
            flush=True,
        )
        raise TimeoutError(
            f"E2E_WALL_BUDGET_FAIL_FAST after {int(elapsed)}s (phase={phase})"
        )
    touch_wall_progress()


def holder_exceeded_wall_budget(holder_elapsed_sec: int) -> bool:
    return int(holder_elapsed_sec) >= int(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)


def holder_progress_stale(holder_progress_at: float | None) -> bool:
    if holder_progress_at is None:
        return True
    return (time.monotonic() - holder_progress_at) >= float(STALL_PROGRESS_SEC)
