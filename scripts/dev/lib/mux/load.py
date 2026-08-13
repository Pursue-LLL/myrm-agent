"""Adaptive mux load probes for Chrome MCP client timeouts.

[INPUT]
- dev_gate.contract::BASE_PAGE_TIMEOUT_MS (POS: Dev Gate 超时与物理池 SSOT)
- cdmcp-mux-autoconnect.mjs status/reap-empty (POS: mux daemon CLI)

[OUTPUT]
- read_mux_status, active_mux_context_count, parallel_open_page_peer_count
- reap_idle_empty_mux_contexts, adaptive_page_timeout_ms

[POS]
Mux 负载探针与 stale empty context 回收；open_mcp_page 并行 peer 计数 SSOT。
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from dev_gate.contract import (
    BASE_PAGE_TIMEOUT_MS,
    BASE_TOOL_TIMEOUT_SEC,
    MAX_PAGE_TIMEOUT_MS,
    PAGE_TIMEOUT_SLOT_MS,
)

_BASE_PAGE_TIMEOUT_MS = int(
    os.environ.get("MYRM_MUX_BASE_PAGE_TIMEOUT_MS", str(BASE_PAGE_TIMEOUT_MS))
)
_PAGE_TIMEOUT_SLOT_MS = int(
    os.environ.get("MYRM_MUX_PAGE_TIMEOUT_SLOT_MS", str(PAGE_TIMEOUT_SLOT_MS))
)
_MAX_PAGE_TIMEOUT_MS = int(
    os.environ.get("MYRM_MUX_MAX_PAGE_TIMEOUT_MS", str(MAX_PAGE_TIMEOUT_MS))
)
_BASE_TOOL_TIMEOUT_SEC = float(
    os.environ.get("MYRM_MUX_BASE_TOOL_TIMEOUT_SEC", str(BASE_TOOL_TIMEOUT_SEC))
)
_MUX_REAP_IDLE_MS_DEFAULT: int = 120_000
_STATUS_CACHE_TTL_SEC = 2.0


def _resolve_mux_bin() -> Path | None:
    override = os.getenv("CDMCP_MUX_BIN", "").strip()
    if override:
        path = Path(override)
        return path if path.is_file() else None
    lib_dir = Path(__file__).resolve().parent
    agent_root = lib_dir.parent.parent.parent
    monorepo_override = os.getenv("MYRM_MONOREPO_ROOT", "").strip()
    monorepo_root = Path(monorepo_override) if monorepo_override else agent_root.parent
    candidate = (
        monorepo_root
        / "scripts"
        / "dev"
        / "cdmcp-mux-autoconnect"
        / "bin"
        / "cdmcp-mux-autoconnect.mjs"
    )
    return candidate if candidate.is_file() else None


@dataclass(frozen=True, slots=True)
class MuxLoadSnapshot:
    mux_contexts: int
    wave_leases: int
    captured_at: float


_status_cache: tuple[float, dict[str, object] | None] | None = None


def read_mux_status(*, force: bool = False) -> dict[str, object] | None:
    global _status_cache
    now = time.monotonic()
    if (
        not force
        and _status_cache is not None
        and now - _status_cache[0] < _STATUS_CACHE_TTL_SEC
    ):
        return _status_cache[1]
    mux_bin = _resolve_mux_bin()
    if mux_bin is None:
        _status_cache = (now, None)
        return None
    try:
        proc = subprocess.run(
            ["node", str(mux_bin), "status"],
            capture_output=True,
            text=True,
            check=False,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        _status_cache = (now, None)
        return None
    if proc.returncode != 0:
        _status_cache = (now, None)
        return None
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        _status_cache = (now, None)
        return None
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        _status_cache = (now, None)
        return None
    _status_cache = (now, payload)
    return payload


def mux_context_count(status: dict[str, object] | None) -> int:
    if status is None:
        return 0
    contexts = status.get("contexts")
    if not isinstance(contexts, list):
        return 0
    return len(contexts)


def active_mux_context_count(status: dict[str, object] | None) -> int:
    """Contexts with at least one owned page — excludes stale empty mux shells."""
    if status is None:
        return 0
    contexts = status.get("contexts")
    if not isinstance(contexts, list):
        return 0
    active = 0
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        pages = ctx.get("ownedPages")
        if isinstance(pages, list) and len(pages) > 0:
            active += 1
    return active


def wave_lease_count(status: dict[str, object] | None) -> int:
    if status is None:
        return 0
    active = status.get("activeLeases")
    if not isinstance(active, list):
        return 0
    return len(active)


def adaptive_page_timeout_ms(*, mux_contexts: int, wave_leases: int = 0) -> int:
    load = max(0, mux_contexts, wave_leases)
    return min(
        _BASE_PAGE_TIMEOUT_MS + load * _PAGE_TIMEOUT_SLOT_MS, _MAX_PAGE_TIMEOUT_MS
    )


def adaptive_tool_timeout_sec(
    *,
    mux_contexts: int,
    wave_leases: int = 0,
    page_timeout_ms: int | None = None,
) -> float:
    nav_ms = (
        page_timeout_ms
        if page_timeout_ms is not None
        else adaptive_page_timeout_ms(
            mux_contexts=mux_contexts, wave_leases=wave_leases
        )
    )
    return max(_BASE_TOOL_TIMEOUT_SEC, nav_ms / 1000.0 + 45.0)


def new_page_stagger_sec(
    *,
    mux_contexts: int,
    wave_leases: int = 0,
    jitter_seed: int = 0,
) -> float:
    """Spread parallel new_page cold starts to avoid mux attachToTarget races."""
    load = max(0, mux_contexts, wave_leases)
    base = min(0.25 + load * 0.3, 2.5)
    jitter = (max(0, jitter_seed) % 97) / 100.0
    return base + jitter


def stale_empty_mux_context_count(status: dict[str, object] | None) -> int:
    """Connected mux contexts with zero owned pages (idle shim shells)."""
    if status is None:
        return 0
    contexts = status.get("contexts")
    if not isinstance(contexts, list):
        return 0
    stale = 0
    for ctx in contexts:
        if not isinstance(ctx, dict):
            continue
        pages = ctx.get("ownedPages")
        if not isinstance(pages, list) or len(pages) == 0:
            stale += 1
    return stale


def parallel_open_page_peer_count(*, signoff: bool = False) -> int:
    """Wave/mux peers for open_mcp_page — active contexts only (P0-A SSOT)."""
    wave = 0
    active_mux = 0
    status = read_mux_status(force=True)
    active_mux = active_mux_context_count(status)
    wave = max(wave, wave_lease_count(status))
    load = snapshot_mux_load(force=True)
    wave = max(wave, int(load.wave_leases))
    if signoff:
        if active_mux > 0:
            return active_mux
        return wave
    peers = max(wave, active_mux)
    if peers > 0:
        return peers
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        monorepo_root = Path(__file__).resolve().parents[5]
        return wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    try:
        from mux.transport_supervisor import _chrome_e2e_pytest_peer_count

        return _chrome_e2e_pytest_peer_count()
    except ImportError:
        return 0


def _reload_mux_daemon_if_needed() -> bool:
    mux_bin = _resolve_mux_bin()
    if mux_bin is None:
        return False
    try:
        proc = subprocess.run(
            ["node", str(mux_bin), "reload-daemon"],
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def solo_gate_cluster_clear() -> bool:
    """Step-1 gate solo cluster: pytest peers=0, wave leases=0, active mux contexts <= 1."""
    try:
        from mux.transport_supervisor import _chrome_e2e_pytest_peer_count

        if _chrome_e2e_pytest_peer_count() != 0:
            return False
    except ImportError:
        return False
    try:
        from e2e_core.api_verify import resolve_e2e_api_context

        ctx = resolve_e2e_api_context(retry_after_apply=False)
        if ctx.active_leases != 0:
            return False
    except Exception:
        return False
    status = read_mux_status(force=True)
    return active_mux_context_count(status) <= 1


def heal_mux_for_solo_gate() -> dict[str, object]:
    """Solo Step-1 gate heal: prune dead cells, reap empty mux shells, reload when idle."""
    pruned_cells = 0
    try:
        from e2e_core.runtime_cell import prune_dead_runtime_cells

        pruned_cells = prune_dead_runtime_cells()
    except ImportError:
        pass

    status = read_mux_status(force=True)
    stale_before = stale_empty_mux_context_count(status)
    active_before = active_mux_context_count(status)
    reaped = 0
    reloaded = False

    if stale_before >= 1 or stale_before + active_before > 1:
        result = reap_idle_empty_mux_contexts(idle_ms=0)
        reaped = int(result.get("reaped", 0) or 0)

    status = read_mux_status(force=True)
    active_after = active_mux_context_count(status)
    total_after = mux_context_count(status)

    pytest_peers = 0
    try:
        from mux.transport_supervisor import _chrome_e2e_pytest_peer_count

        pytest_peers = _chrome_e2e_pytest_peer_count()
    except ImportError:
        pass

    if pytest_peers == 0 and (active_after > 1 or total_after > 1):
        reloaded = _reload_mux_daemon_if_needed()
        if reloaded:
            global _status_cache
            _status_cache = None
            status = read_mux_status(force=True)
            active_after = active_mux_context_count(status)
            total_after = mux_context_count(status)

    return {
        "prunedCells": pruned_cells,
        "staleBefore": stale_before,
        "activeBefore": active_before,
        "reaped": reaped,
        "activeAfter": active_after,
        "totalAfter": total_after,
        "reloaded": reloaded,
        "pytestPeers": pytest_peers,
    }


def reap_idle_empty_mux_contexts(*, idle_ms: int | None = None) -> dict[str, object]:
    """Ask mux daemon to destroy idle empty contexts (P0-A stale shell reap)."""
    global _status_cache
    mux_bin = _resolve_mux_bin()
    if mux_bin is None:
        return {"ok": False, "reason": "mux_bin_missing", "reaped": 0}
    resolved_idle_ms = (
        int(idle_ms)
        if idle_ms is not None
        else int(os.environ.get("MUX_REAP_IDLE_MS", str(_MUX_REAP_IDLE_MS_DEFAULT)))
    )

    def _invoke() -> dict[str, object]:
        try:
            proc = subprocess.run(
                ["node", str(mux_bin), "reap-empty"],
                capture_output=True,
                text=True,
                check=False,
                timeout=12,
                env={
                    **os.environ,
                    "MUX_REAP_IDLE_MS": str(resolved_idle_ms),
                },
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"ok": False, "reason": str(exc), "reaped": 0}
        if proc.returncode != 0:
            return {
                "ok": False,
                "reason": (proc.stderr or proc.stdout or "reap_empty_failed").strip(),
                "reaped": 0,
            }
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return {"ok": False, "reason": "invalid_json", "reaped": 0}
        if not isinstance(payload, dict):
            return {"ok": False, "reason": "invalid_payload", "reaped": 0}
        if payload.get("ok") is not True:
            reason = str(payload.get("reason") or "reap_empty_failed")
            return {
                "ok": False,
                "reason": reason,
                "reaped": 0,
                "code": payload.get("code"),
            }
        reaped_raw = payload.get("reaped")
        reaped = int(reaped_raw) if isinstance(reaped_raw, int) else 0
        return {
            "ok": True,
            "reaped": reaped,
            "remaining": payload.get("remaining"),
            "idleMs": payload.get("idleMs", resolved_idle_ms),
        }

    result = _invoke()
    if result.get("ok") is True:
        _status_cache = None
        return result
    reason = str(result.get("reason") or "")
    if "Method not found" in reason or result.get("code") == -32601:
        parallel_peers = 0
        try:
            from mux.transport_supervisor import _chrome_e2e_pytest_peer_count

            parallel_peers = _chrome_e2e_pytest_peer_count()
        except ImportError:
            parallel_peers = 0
        if parallel_peers > 1:
            return {
                "ok": False,
                "reason": "reload_deferred_parallel_pytest",
                "reaped": 0,
                "parallel_peers": parallel_peers,
            }
        if _reload_mux_daemon_if_needed():
            result = _invoke()
            if result.get("ok") is True:
                _status_cache = None
    return result


def snapshot_mux_load(
    *,
    wave_status: dict[str, object] | None = None,
    force: bool = False,
) -> MuxLoadSnapshot:
    mux_status = read_mux_status(force=force)
    return MuxLoadSnapshot(
        mux_contexts=mux_context_count(mux_status),
        wave_leases=wave_lease_count(wave_status),
        captured_at=time.monotonic(),
    )
