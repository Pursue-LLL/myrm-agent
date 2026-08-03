"""Peer count SSOT — single source for pytest/mux/signoff peer metrics (P0-A).

[OUTPUT]
- chrome_e2e_pytest_peer_count()
- solo_gate_active_mux_peer_count()
- parallel_active_test_count_ssot()
"""

from __future__ import annotations

import os
import subprocess


def _process_ancestor_pids(pid: int, *, max_depth: int = 24) -> frozenset[int]:
    """Walk parent chain including pid itself."""
    seen: set[int] = {pid}
    current = pid
    for _ in range(max_depth):
        try:
            ps_proc = subprocess.run(
                ["ps", "-p", str(current), "-o", "ppid="],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            break
        if ps_proc.returncode != 0:
            break
        ppid_raw = ps_proc.stdout.strip()
        if not ppid_raw.isdigit():
            break
        ppid = int(ppid_raw)
        if ppid <= 1 or ppid in seen:
            break
        seen.add(ppid)
        current = ppid
    return frozenset(seen)


def _active_session_owner_pids() -> frozenset[int] | None:
    """Owner PIDs for non-terminal Dev Gate sessions; None when store unavailable."""
    try:
        from dev_gate_store import DevGateStore, default_store_path

        store = DevGateStore(default_store_path())
        owners = {record.owner_pid for record in store.list_active() if record.owner_pid > 0}
        return frozenset(owners)
    except OSError:
        return None


def _pytest_pid_serves_active_session(pid: int, owners: frozenset[int]) -> bool:
    if not owners:
        return False
    return bool(_process_ancestor_pids(pid) & owners)


def chrome_e2e_pytest_peer_count() -> int:
    """Live python -m pytest chrome_e2e workers; excludes run_pytest_safe wrapper."""
    owners = _active_session_owner_pids()
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
        pid = int(pid_raw)
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
        if owners is not None and not _pytest_pid_serves_active_session(pid, owners):
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
