"""How busy the shared Chrome stack is: parallel-session detection and the waits that scale with it."""

from __future__ import annotations

import os
import time
from pathlib import Path

from dev_gate.contract import SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC, is_e2e_signoff_runtime


def _warm_ui_parallel_wait_sec(base_wait_sec: float) -> float:
    """Extend warm budget when wave leases or parallel chrome_e2e peers contend for shared UI."""
    try:
        from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            # Flock serializes compile bursts — do not multiply per-lane wall by peer count.
            return base_wait_sec
    except ImportError:
        pass
    monorepo_root = Path(__file__).resolve().parents[5]
    try:
        from dev_gate.contract import (
            phase_c_burst_lane_count,
            shared_ui_hydrate_wait_sec,
        )
        from e2e_core.stack_mutation_policy import wave_active_lease_count
        from mux.transport_supervisor import parallel_active_test_count

        burst_lanes = phase_c_burst_lane_count()
        wave_leases = wave_active_lease_count(monorepo_root)
        active_tests = parallel_active_test_count()
        if burst_lanes >= 2:
            # Phase C burst: scale by declared lane width, not foreign daily peers.
            active = max(burst_lanes, min(wave_leases, burst_lanes + 1))
        else:
            active = max(wave_leases, active_tests)
        if active > 0:
            cap = float(shared_ui_hydrate_wait_sec())
            return min(base_wait_sec + active * 45.0, cap)
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return base_wait_sec


def _bounded_settings_ui_wait_sec(base_wait_sec: float) -> float:
    cap = float(SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC) if is_e2e_signoff_runtime() else 90.0
    parallel = _parallel_chrome_e2e_active()
    if parallel and is_e2e_signoff_runtime():
        cap = max(cap, 180.0)
    elif parallel:
        # Dev parallel: settings turbopack compile needs multiple reload heals.
        cap = min(cap, 120.0)
    return min(_warm_ui_parallel_wait_sec(base_wait_sec), cap)


def _settings_heal_reload_timeout_ms(*, base_ms: int = 120_000) -> int:
    if _parallel_chrome_e2e_active():
        return min(base_ms, 90_000)
    return base_ms


_PARALLEL_ACTIVE_CACHE_TTL_SEC = 600.0
_parallel_active_cache: tuple[float, bool] | None = None


def _parallel_chrome_e2e_active() -> bool:
    """Fast parallel probe for wait_for_state hot path — never pgrep/ps on poll loop."""
    global _parallel_active_cache
    now = time.monotonic()
    if _parallel_active_cache is not None:
        cached_at, cached = _parallel_active_cache
        if now - cached_at < _PARALLEL_ACTIVE_CACHE_TTL_SEC:
            return cached
    for key in ("MYRM_E2E_PARALLEL_ACTIVE_LEASES", "MYRM_E2E_PHASE_C_BURST_LANES"):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit() and int(raw) >= 2:
            _parallel_active_cache = (now, True)
            return True
    raw_count = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_COUNT", "").strip()
    if raw_count.isdigit() and int(raw_count) >= 2:
        _parallel_active_cache = (now, True)
        return True
    if raw_count.isdigit() and int(raw_count) <= 1:
        _parallel_active_cache = (now, False)
        return False
    active = _parallel_chrome_e2e_active_from_context()
    _parallel_active_cache = (now, active)
    return active


def _parallel_chrome_e2e_active_from_context() -> bool:
    """Read coordinator snapshot — file-only, no subprocess."""
    state_dir = os.environ.get(
        "MYRM_DEV_STATE_DIR",
        str(Path.home() / ".local" / "state" / "myrm-dev"),
    )
    context_path = Path(state_dir) / "e2e-context.json"
    if not context_path.is_file():
        return False
    try:
        import json

        payload = json.loads(context_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return False
    leases = payload.get("active_leases")
    if isinstance(leases, int) and leases >= 2:
        return True
    active_tests = payload.get("active_tests")
    if isinstance(active_tests, list) and len(active_tests) >= 2:
        return True
    return False


def _parallel_open_page_peer_count() -> int:
    """Wave/mux peers for open_mcp_page heal policy."""
    from mux.load import parallel_open_page_peer_count

    return parallel_open_page_peer_count(signoff=is_e2e_signoff_runtime())
