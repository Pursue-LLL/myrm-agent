"""Peer count SSOT — single source for pytest/mux/signoff peer metrics (P0-A).

[OUTPUT]
- chrome_e2e_pytest_peer_count()
- solo_gate_active_mux_peer_count()
- parallel_active_test_count_ssot()
"""

from __future__ import annotations

import os
import subprocess


def chrome_e2e_pytest_peer_count() -> int:
    """Live python -m pytest chrome_e2e workers; excludes run_pytest_safe wrapper."""
    try:
        proc = subprocess.run(
            ["pgrep", "-f", r"python -m pytest.*chrome_e2e"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return parallel_active_test_count_ssot()
    if proc.returncode != 0:
        return 0
    peers = 0
    for line in proc.stdout.splitlines():
        pid_raw = line.strip()
        if not pid_raw.isdigit():
            continue
        try:
            ps_proc = subprocess.run(
                ["ps", "-p", pid_raw, "-o", "args="],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            peers += 1
            continue
        cmd = ps_proc.stdout.strip()
        if "run_pytest_safe" in cmd or "--collect-only" in cmd:
            continue
        peers += 1
    return peers


def solo_gate_active_mux_peer_count() -> int:
    """Active mux contexts with owned pages — Step1 solo gate SSOT."""
    from mux_load import active_mux_context_count, read_mux_status

    return active_mux_context_count(read_mux_status(force=True))


def parallel_active_test_count_ssot() -> int:
    """Parallel chrome_e2e count for recovery mutex scaling."""
    pytest_peers = chrome_e2e_pytest_peer_count()
    if pytest_peers > 0:
        return pytest_peers
    raw = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_COUNT", "").strip()
    if raw.isdigit():
        return max(1, int(raw))
    try:
        from e2e_runtime_cell import prune_dead_runtime_cells

        prune_dead_runtime_cells()
    except ImportError:
        pass
    return 1
