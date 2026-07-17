"""Adaptive mux load probes for Chrome MCP client timeouts."""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from dev_gate_contract import (
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


def wave_lease_count(status: dict[str, object] | None) -> int:
    if status is None:
        return 0
    active = status.get("activeLeases")
    if not isinstance(active, list):
        return 0
    return len(active)


def adaptive_page_timeout_ms(*, mux_contexts: int, wave_leases: int = 0) -> int:
    load = max(0, mux_contexts, wave_leases)
    return min(_BASE_PAGE_TIMEOUT_MS + load * _PAGE_TIMEOUT_SLOT_MS, _MAX_PAGE_TIMEOUT_MS)


def adaptive_tool_timeout_sec(
    *,
    mux_contexts: int,
    wave_leases: int = 0,
    page_timeout_ms: int | None = None,
) -> float:
    nav_ms = (
        page_timeout_ms
        if page_timeout_ms is not None
        else adaptive_page_timeout_ms(mux_contexts=mux_contexts, wave_leases=wave_leases)
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
