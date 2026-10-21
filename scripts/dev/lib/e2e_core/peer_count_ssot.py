"""Peer count SSOT — single source for pytest/mux/signoff peer metrics (P0-A).

[OUTPUT]
- chrome_e2e_pytest_peer_count()
- solo_gate_active_mux_peer_count()
- parallel_active_test_count_ssot()
"""

from __future__ import annotations

import os
import subprocess
import time

_PEER_PROBE_TIMEOUT_SEC = 1.0
_PEER_SCAN_WALL_SEC = 2.5
_MAX_PIDS_PER_SCAN = 8
_ANCESTOR_MAX_DEPTH = 6
_PEER_COUNT_CACHE_TTL_SEC = 5.0
_PARALLEL_COUNT_CACHE_TTL_SEC = 5.0
_pytest_peer_count_cache: tuple[float, int] | None = None
_parallel_count_cache: tuple[float, int] | None = None


def clear_pytest_peer_count_cache() -> None:
    """Invalidate cached pgrep peer count after signoff reap."""
    global _pytest_peer_count_cache, _parallel_count_cache
    _pytest_peer_count_cache = None
    _parallel_count_cache = None


def _run_subprocess_probe(args: list[str]) -> subprocess.CompletedProcess[str] | None:
    """Bounded pgrep/ps probe — must not block mux request-lock hot path under load."""
    try:
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            timeout=_PEER_PROBE_TIMEOUT_SEC,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _process_ancestor_pids(
    pid: int,
    *,
    max_depth: int = _ANCESTOR_MAX_DEPTH,
    wall_deadline: float | None = None,
) -> frozenset[int]:
    """Walk parent chain including pid itself."""
    seen: set[int] = {pid}
    current = pid
    for _ in range(max_depth):
        if wall_deadline is not None and time.monotonic() >= wall_deadline:
            break
        ps_proc = _run_subprocess_probe(["ps", "-p", str(current), "-o", "ppid="])
        if ps_proc is None:
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
        from dev_gate.store import DevGateStore, default_store_path

        store = DevGateStore(default_store_path())
        owners = {
            record.owner_pid for record in store.list_active() if record.owner_pid > 0
        }
        return frozenset(owners)
    except OSError:
        return None


def _pytest_pid_serves_active_session(
    pid: int,
    owners: frozenset[int],
    *,
    wall_deadline: float | None = None,
) -> bool:
    if not owners:
        return False
    return bool(
        _process_ancestor_pids(pid, wall_deadline=wall_deadline) & owners
    )


def chrome_e2e_pytest_peer_count() -> int:
    """Live python -m pytest chrome_e2e workers; excludes run_pytest_safe wrapper."""
    global _pytest_peer_count_cache
    now = time.monotonic()
    if _pytest_peer_count_cache is not None:
        cached_at, cached = _pytest_peer_count_cache
        if now - cached_at < _PEER_COUNT_CACHE_TTL_SEC:
            return cached

    owners = _active_session_owner_pids()
    proc = _run_subprocess_probe(["pgrep", "-f", r"python -m pytest.*chrome_e2e"])
    if proc is None:
        _pytest_peer_count_cache = (now, 0)
        return 0
    if proc.returncode != 0:
        _pytest_peer_count_cache = (now, 0)
        return 0
    peers = 0
    wall_deadline = now + _PEER_SCAN_WALL_SEC
    for line in proc.stdout.splitlines()[:_MAX_PIDS_PER_SCAN]:
        if time.monotonic() >= wall_deadline:
            break
        pid_raw = line.strip()
        if not pid_raw.isdigit():
            continue
        pid = int(pid_raw)
        ps_proc = _run_subprocess_probe(["ps", "-p", pid_raw, "-o", "args="])
        if ps_proc is None:
            peers += 1
            continue
        cmd = ps_proc.stdout.strip()
        if "run_pytest_safe" in cmd or "--collect-only" in cmd:
            continue
        if owners is not None and not _pytest_pid_serves_active_session(
            pid, owners, wall_deadline=wall_deadline
        ):
            continue
        peers += 1
    _pytest_peer_count_cache = (now, peers)
    return peers


def solo_gate_active_mux_peer_count() -> int:
    """Active mux contexts with owned pages — Step1 solo gate SSOT."""
    from mux.load import active_mux_context_count, read_mux_status

    return active_mux_context_count(read_mux_status(force=True))


def parallel_active_test_count_ssot() -> int:
    """Parallel chrome_e2e count for recovery mutex scaling."""
    global _parallel_count_cache
    now = time.monotonic()
    if _parallel_count_cache is not None:
        cached_at, cached = _parallel_count_cache
        if now - cached_at < _PARALLEL_COUNT_CACHE_TTL_SEC:
            return cached

    env_peers = 0
    for key in ("MYRM_E2E_PARALLEL_ACTIVE_LEASES", "MYRM_E2E_PARALLEL_ACTIVE_COUNT"):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            env_peers = max(env_peers, int(raw))
    if env_peers >= 2:
        _parallel_count_cache = (now, env_peers)
        return env_peers

    pytest_peers = chrome_e2e_pytest_peer_count()
    session_peers = 0
    # Never full-session ps scan on the evaluate hot path while a chrome_e2e BODY is active.
    if pytest_peers < 2 and not os.environ.get("MYRM_E2E_RUN_ID", "").strip():
        try:
            from e2e_session_runtime.registry import list_live_e2e_sessions

            session_peers = len(list_live_e2e_sessions())
        except ImportError:
            session_peers = 0
    combined = max(pytest_peers, session_peers, env_peers)
    if combined > 0:
        _parallel_count_cache = (now, combined)
        return combined
    raw = os.environ.get("MYRM_E2E_PARALLEL_ACTIVE_COUNT", "").strip()
    if raw.isdigit():
        result = max(1, int(raw))
        _parallel_count_cache = (now, result)
        return result
    try:
        from e2e_core.runtime_cell import prune_dead_runtime_cells

        prune_dead_runtime_cells()
    except ImportError:
        pass
    _parallel_count_cache = (now, 1)
    return 1
