"""Live pressure readings that scale budgets under parallel runs: wave leases, live sessions and signoff peers.

Other modules read them through this module (`parallel_pressure.<name>()`), so one patch point reaches every reader."""

from __future__ import annotations

import os
import time


def wave_active_lease_count_for_mux() -> int:
    try:
        from pathlib import Path

        from e2e_core.stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[6]
        return max(0, wave_active_lease_count(monorepo_root))
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


def parallel_chrome_e2e_pressure() -> int:
    """Wave leases plus live ADMIT/BODY sessions — drives attach UI probe scaling."""
    pressure = wave_active_lease_count_for_mux()
    try:
        from e2e_session_runtime.registry import list_live_e2e_sessions

        pressure = max(pressure, len(list_live_e2e_sessions()))
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return max(0, pressure)


_PARALLEL_SIGNOFF_PRESSURE_CACHE: tuple[float, int] | None = None


def parallel_signoff_pressure_peers() -> int:
    """Cheap session-plane pressure for wall scaling; never live-probe mux here."""
    global _PARALLEL_SIGNOFF_PRESSURE_CACHE

    raw = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_COUNT", "").strip()
    if raw.isdigit():
        return max(0, int(raw))
    now = time.monotonic()
    if (
        _PARALLEL_SIGNOFF_PRESSURE_CACHE is not None
        and now - _PARALLEL_SIGNOFF_PRESSURE_CACHE[0] <= 2.0
    ):
        return _PARALLEL_SIGNOFF_PRESSURE_CACHE[1]
    # Wall-budget calculation is on the launch hot path. Wave leases are the
    # session SSOT; forcing mux/CDP status here made every helper subprocess
    # block for 10–20 seconds under load and multiplied admit latency.
    pressure = wave_active_lease_count_for_mux()
    _PARALLEL_SIGNOFF_PRESSURE_CACHE = (now, max(0, pressure))
    return max(0, pressure)
