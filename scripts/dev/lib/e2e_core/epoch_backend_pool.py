"""Epoch-keyed shared backend pool — single-flight, refcount, safe drain, crash rebuild.

[INPUT]
- verify_backend_seed (POS: verify-api runtime allocation and health/epoch probes)
- isolated_runtime.registry (POS: process liveness and runtime records)

[OUTPUT]
- epoch_fingerprint_single_flight(): per-fingerprint fcntl lock preventing duplicate cold boots
- register_epoch_backend_holder() / release_epoch_backend_holder(): PID-backed refcount with grace window
- has_active_epoch_holders() / find_pooled_epoch_backend() / invalidate_epoch_backend()

[POS]
M2 Epoch Backend Pool layer — ensures one shared backend per source_fingerprint F,
protects in-flight sessions on old epochs until refcount reaches zero, and supports
automatic crash eviction and rebuild.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

POOL_REGISTRY_FILENAME: Final[str] = "epoch-pool-registry.json"
POOL_LOCK_FILENAME: Final[str] = "epoch-pool-registry.lock"
PREPIN_GRACE_SEC: Final[float] = 90.0


@dataclass(frozen=True, slots=True)
class PooledBackendCandidate:
    runtime_id: str
    api_base: str
    owner_token: str
    fingerprint: str


def _pool_root(isolated_root: Path) -> Path:
    root = isolated_root / "epoch-pool"
    root.mkdir(parents=True, exist_ok=True)
    return root


@contextmanager
def epoch_fingerprint_single_flight(
    *,
    isolated_root: Path,
    fingerprint: str,
) -> Iterator[None]:
    """Serialize cold-boot attempts for the same workspace source_fingerprint."""
    safe_fp = "".join(ch for ch in fingerprint if ch.isalnum() or ch in ("-", "_"))
    lock_name = f"single-flight-{safe_fp or 'default'}.lock"
    lock_path = _pool_root(isolated_root) / lock_name
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _locked_pool_state(isolated_root: Path) -> Iterator[tuple[Path, dict[str, object]]]:
    root = _pool_root(isolated_root)
    lock_path = root / POOL_LOCK_FILENAME
    state_path = root / POOL_REGISTRY_FILENAME
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            state = _read_pool_state(state_path)
            yield state_path, state
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_pool_state(state_path: Path) -> dict[str, object]:
    if not state_path.is_file():
        return {"backends": {}}
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {"backends": {}}
    if not isinstance(raw, dict) or not isinstance(raw.get("backends"), dict):
        return {"backends": {}}
    return raw


def _write_pool_state(state_path: Path, state: dict[str, object]) -> None:
    tmp_path = state_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    tmp_path.replace(state_path)


def _pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False


def _prune_live_holders(raw_holders: object) -> dict[str, float]:
    if not isinstance(raw_holders, dict):
        return {}
    live: dict[str, float] = {}
    for pid_str, ts_val in raw_holders.items():
        try:
            pid = int(pid_str)
            ts = float(ts_val)
        except (TypeError, ValueError):
            continue
        if _pid_is_alive(pid):
            live[str(pid)] = ts
    return live


def default_holder_pid() -> int:
    """Resolve the session-owning PID so short-lived CLI callers credit their parent."""
    raw = os.environ.get("MYRM_E2E_EPOCH_HOLDER_PID", "").strip()
    if raw:
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return os.getpid()


def register_epoch_backend_holder(
    *,
    isolated_root: Path,
    runtime_id: str,
    api_base: str,
    fingerprint: str = "",
    owner_token: str = "",
    holder_pid: int | None = None,
    grace_sec: float = PREPIN_GRACE_SEC,
) -> int:
    """Record a live session holder PID on ``runtime_id`` and return active refcount."""
    if not runtime_id:
        return 0
    pid = holder_pid if holder_pid is not None else default_holder_pid()
    now = time.time()
    with _locked_pool_state(isolated_root) as (state_path, state):
        backends = state.setdefault("backends", {})
        if not isinstance(backends, dict):
            backends = {}
            state["backends"] = backends
        entry = backends.get(runtime_id)
        if not isinstance(entry, dict):
            entry = {}
        holders = _prune_live_holders(entry.get("holders"))
        if pid > 0 and _pid_is_alive(pid):
            holders[str(pid)] = now
        prev_grace = entry.get("graceUntil")
        prev_grace_f = float(prev_grace) if isinstance(prev_grace, (int, float)) else 0.0
        clean_fp = fingerprint if isinstance(fingerprint, str) else ""
        clean_tok = owner_token if isinstance(owner_token, str) else ""
        entry.update(
            {
                "runtimeId": str(runtime_id),
                "apiBase": str(api_base).rstrip("/"),
                "fingerprint": clean_fp or str(entry.get("fingerprint") or ""),
                "ownerToken": clean_tok or str(entry.get("ownerToken") or ""),
                "holders": holders,
                "graceUntil": max(prev_grace_f, now + max(0.0, grace_sec)),
                "updatedAt": now,
            }
        )
        backends[runtime_id] = entry
        _write_pool_state(state_path, state)
        return len(holders)


def release_epoch_backend_holder(
    *,
    isolated_root: Path,
    runtime_id: str,
    holder_pid: int | None = None,
) -> int:
    """Remove ``holder_pid`` from ``runtime_id`` and return remaining live refcount."""
    if not runtime_id:
        return 0
    pid = holder_pid if holder_pid is not None else default_holder_pid()
    with _locked_pool_state(isolated_root) as (state_path, state):
        backends = state.get("backends")
        if not isinstance(backends, dict):
            return 0
        entry = backends.get(runtime_id)
        if not isinstance(entry, dict):
            return 0
        holders = _prune_live_holders(entry.get("holders"))
        holders.pop(str(pid), None)
        entry["holders"] = holders
        entry["graceUntil"] = 0.0
        entry["updatedAt"] = time.time()
        backends[runtime_id] = entry
        _write_pool_state(state_path, state)
        return len(holders)


def has_active_epoch_holders(
    *,
    isolated_root: Path,
    runtime_id: str,
) -> bool:
    """True when ``runtime_id`` has any live holder PID or an active pre-pin grace window."""
    if not runtime_id:
        return False
    now = time.time()
    with _locked_pool_state(isolated_root) as (state_path, state):
        backends = state.get("backends")
        if not isinstance(backends, dict):
            return False
        entry = backends.get(runtime_id)
        if not isinstance(entry, dict):
            return False
        holders = _prune_live_holders(entry.get("holders"))
        entry["holders"] = holders
        backends[runtime_id] = entry
        _write_pool_state(state_path, state)
        if holders:
            return True
        grace_until = entry.get("graceUntil")
        return isinstance(grace_until, (int, float)) and now < float(grace_until)


def invalidate_epoch_backend(
    *,
    isolated_root: Path,
    runtime_id: str = "",
    api_base: str = "",
) -> None:
    """Evict a crashed/unhealthy backend from the pool registry."""
    clean_api = api_base.rstrip("/")
    with _locked_pool_state(isolated_root) as (state_path, state):
        backends = state.get("backends")
        if not isinstance(backends, dict):
            return
        to_remove = [
            rid
            for rid, entry in backends.items()
            if (runtime_id and rid == runtime_id)
            or (
                clean_api
                and isinstance(entry, dict)
                and str(entry.get("apiBase") or "").rstrip("/") == clean_api
            )
        ]
        for rid in to_remove:
            backends.pop(rid, None)
        if to_remove:
            _write_pool_state(state_path, state)


def find_pooled_epoch_backend(
    *,
    isolated_root: Path,
    fingerprint: str,
    warm_pool_ids: set[str] | None = None,
) -> list[PooledBackendCandidate]:
    """Return active ``verify-api-*`` registry candidates so peers share one backend per epoch."""
    if not fingerprint:
        return []
    registry_path = isolated_root / "registry.json"
    if not registry_path.is_file():
        return []
    try:
        raw = json.loads(registry_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return []
    if not isinstance(raw, dict):
        return []
    records = raw.get("runtimes") if isinstance(raw.get("runtimes"), dict) else raw
    if not isinstance(records, dict):
        return []
    excluded = warm_pool_ids or set()
    found: list[ tuple[float, PooledBackendCandidate] ] = []
    for record in records.values():
        if not isinstance(record, dict):
            continue
        if not record.get("backendOnly") or record.get("reapable") is not False:
            continue
        rid = str(record.get("runtimeId") or "")
        if not rid.startswith("verify-api-") or rid in excluded:
            continue
        if record.get("phase") not in {"allocated", "bootstrapping", "running"}:
            continue
        try:
            port = int(record.get("backendPort") or 0)
            hb = float(record.get("heartbeatAt") or 0.0)
        except (TypeError, ValueError):
            continue
        if port <= 0:
            continue
        found.append(
            (
                hb,
                PooledBackendCandidate(
                    runtime_id=rid,
                    api_base=f"http://127.0.0.1:{port}",
                    owner_token=str(record.get("ownerToken") or ""),
                    fingerprint=fingerprint,
                ),
            )
        )
    found.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in found]
