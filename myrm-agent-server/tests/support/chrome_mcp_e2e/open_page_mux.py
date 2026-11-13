"""Mux-facing guards of opening a page: the scoped attach restart and the CDP readiness probe."""

from __future__ import annotations

import os
import time
from pathlib import Path

from cdp_chat.support import wait_e2e_cdp_ready
from dev_gate.contract import is_e2e_signoff_runtime
from e2e_core.orchestrator import touch_wall_progress

from tests.support.e2e_runtime_guard import heartbeat_once

from .parallel_load import _parallel_open_page_peer_count


def _should_skip_attach_preflight_restart() -> bool:
    """P0-B: global mux attach restart must not run under active parallel load."""
    try:
        from mux.load import snapshot_mux_load

        load = snapshot_mux_load(force=True)
        if max(0, load.mux_contexts, load.wave_leases) > 0:
            return True
    except (ImportError, OSError, TypeError, ValueError):
        pass
    return _parallel_open_page_peer_count() >= 2


def _open_page_cdp_probe_budget_sec() -> float:
    """Scale CDP+mux preflight budget under parallel wave/mux load."""
    base = 45.0
    max_budget = 240.0 if is_e2e_signoff_runtime() else 180.0
    peers = 0
    try:
        from mux.load import snapshot_mux_load

        load = snapshot_mux_load()
        peers = max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if peers <= 0:
        monorepo_root = Path(__file__).resolve().parents[5]
        try:
            from e2e_core.stack_mutation_policy import wave_active_lease_count

            peers = wave_active_lease_count(monorepo_root)
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
    if peers <= 0:
        return base
    return min(base + peers * 12.0, max_budget)


def _force_mux_attach_restart_after_new_page_timeout() -> None:
    """Restart mux daemon when tools/list probe passes but new_page hangs (attach heal)."""
    if _should_skip_attach_preflight_restart():
        return
    import sys

    lib_dir = Path(__file__).resolve().parents[4] / "scripts" / "dev" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="open_mcp_page new_page timeout")


def _require_e2e_cdp_ready(*, budget_sec: float | None = None) -> None:
    """Wait until the Chrome CDP endpoint answers; raise when it stays down for the whole probe budget."""

    port = int(os.environ.get("MYRM_CHROME_E2E_PORT", "9333"))
    wait_budget = budget_sec if budget_sec is not None else _open_page_cdp_probe_budget_sec()
    deadline = time.monotonic() + wait_budget

    while time.monotonic() < deadline:
        heartbeat_once()
        touch_wall_progress(current_node="open_mcp_page_cdp_probe")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if wait_e2e_cdp_ready(
            timeout_sec=min(5.0, max(1.0, remaining)),
            port=port,
        ):
            return
        time.sleep(1.0)
    raise RuntimeError(f"CDP endpoint not ready after {wait_budget:.0f}s on :{port}")
