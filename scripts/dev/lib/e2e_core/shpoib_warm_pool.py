"""SHPOIB warm backend pool for LIVE chrome_e2e (R159): registry, borrow, release.

[POS] Dev Gate layer. Keeps hot private backends ready for borrow to cut
cold bootstrap (~89s) to near-zero on pool hit. Pattern derived from flock + registry + progress tokens (R159).
Registry sections are short by contract (``_registry_lock``); booting backends lives in
``shpoib_warm_refill`` so a spawn can never sit under the lock borrowers wait on.
"""

from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, TypedDict

from e2e_core.real_user_home import real_user_home

DEFAULT_POOL_SIZE: Final[int] = 2
_LOCK_WAIT_REPORT_SEC: Final[float] = 2.0
_SCHEMA_VERSION: Final[int] = 1


class WarmBackendRecord(TypedDict, total=False):
    runtimeId: str
    ownerToken: str
    apiBase: str
    state: str
    ownerPid: int
    heartbeatAt: float
    acquiredAt: float
    sourceFingerprint: str


class WarmPoolRegistry(TypedDict):
    schemaVersion: int
    backends: dict[str, WarmBackendRecord]


@dataclass(frozen=True, slots=True)
class WarmBorrowResult:
    ok: bool
    runtime_id: str
    owner_token: str
    api_base: str
    detail: str
    environment: dict[str, str]


def _pool_root() -> Path:
    raw = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(raw) if raw else real_user_home() / ".local/state/myrm-dev"
    return base / "shpoib-warm-pool"


def _registry_path() -> Path:
    return _pool_root() / "registry.json"


def _lock_path() -> Path:
    return _pool_root() / "registry.lock"


def _refill_lock_path() -> Path:
    return _pool_root() / "refill.lock"


@contextmanager
def _registry_lock() -> Iterator[None]:
    """Serialise registry read-modify-write sections.

    Hold it for milliseconds, never across a backend spawn: a cold boot takes
    minutes, and every borrower and releaser queues on this lock, so a spawn
    under it stalls each PRIVATE session that reaches setup in the meantime.
    """
    _pool_root().mkdir(parents=True, exist_ok=True)
    with _lock_path().open("a+", encoding="utf-8") as handle:
        queued_at = time.monotonic()
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        waited = time.monotonic() - queued_at
        if waited >= _LOCK_WAIT_REPORT_SEC:
            print(f"E2E_SHPOIB_WARM_POOL_LOCK_WAIT: waited={waited:.0f}s", file=sys.stderr)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def _refill_slot() -> Iterator[bool]:
    """Single-flight refill: yields False when another process is already refilling."""
    _pool_root().mkdir(parents=True, exist_ok=True)
    with _refill_lock_path().open("a+", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _load_registry() -> WarmPoolRegistry:
    path = _registry_path()
    if not path.is_file():
        return {"schemaVersion": _SCHEMA_VERSION, "backends": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schemaVersion": _SCHEMA_VERSION, "backends": {}}
    if not isinstance(payload, dict):
        return {"schemaVersion": _SCHEMA_VERSION, "backends": {}}
    backends_raw = payload.get("backends")
    backends: dict[str, WarmBackendRecord] = {}
    if isinstance(backends_raw, dict):
        for key, raw in backends_raw.items():
            if isinstance(raw, dict) and isinstance(key, str):
                backends[key] = raw  # type: ignore[assignment]
    return {"schemaVersion": _SCHEMA_VERSION, "backends": backends}


def _save_registry(registry: WarmPoolRegistry) -> None:
    root = _pool_root()
    root.mkdir(parents=True, exist_ok=True)
    path = _registry_path()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _fetch_health_payload(api_base: str) -> dict[str, object] | None:
    """Fetch ``/api/v1/health`` and return its payload dict, or None on any failure."""
    url = f"{api_base.rstrip('/')}/api/v1/health"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            if not (200 <= resp.status < 300):
                return None
            payload = json.loads(resp.read().decode("utf-8"))
    except (
        urllib.error.URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ):
        return None
    return payload if isinstance(payload, dict) else None


def warm_backend_health_ok(api_base: str, runtime_id: str) -> bool:
    """Quick probe before borrow — stale registry rows must not block LIVE bootstrap."""
    payload = _fetch_health_payload(api_base)
    if payload is None:
        return False
    if payload.get("status") != "healthy":
        return False
    observed = str(payload.get("runtime_id") or "").strip()
    return not observed or observed == runtime_id


def warm_backend_source_fingerprint(api_base: str) -> str:
    """Source fingerprint of a warm backend, from ``stack_epoch.source_fingerprint``.

    Empty string when the endpoint is unreachable or the field is absent —
    callers treat empty as "unknown" (fail-open) rather than stale.
    """
    payload = _fetch_health_payload(api_base)
    if payload is None:
        return ""
    stack_epoch = payload.get("stack_epoch")
    if not isinstance(stack_epoch, dict):
        return ""
    fingerprint = stack_epoch.get("source_fingerprint")
    return fingerprint.strip() if isinstance(fingerprint, str) else ""


@lru_cache(maxsize=1)
def _workspace_source_fingerprint() -> str:
    """Current workspace backend source fingerprint (lazy; cached per process)."""
    try:
        from e2e_core.runtime_identity import _backend_source_fingerprint
    except ImportError:
        return ""
    try:
        return _backend_source_fingerprint()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _record_is_stale(record: WarmBackendRecord, *, now: float) -> bool:
    owner_pid = record.get("ownerPid")
    heartbeat_at = record.get("heartbeatAt")
    state = record.get("state")
    if not isinstance(owner_pid, int) or not isinstance(heartbeat_at, (int, float)):
        return True
    if not _pid_alive(owner_pid):
        # Zombie: borrowed backend whose owner died before release_warm_backend.
        # Leaving it would leak a dead row (user rule: no zombie residue).
        return True
    if now - float(heartbeat_at) > 900.0 and state != "borrowed":
        return True
    if state == "borrowed":
        return False
    api_base = record.get("apiBase")
    runtime_id = str(record.get("runtimeId") or "")
    if not isinstance(api_base, str) or not runtime_id:
        return True
    if not warm_backend_health_ok(api_base, runtime_id):
        return True
    # §26.26: a backend spawned from older source must not linger in the pool —
    # borrowing it would run tests against stale code.
    stored_fp = record.get("sourceFingerprint")
    if isinstance(stored_fp, str) and stored_fp:
        workspace_fp = _workspace_source_fingerprint()
        if workspace_fp and stored_fp != workspace_fp:
            return True
    return False


def _release_pruned_runtime(record: WarmBackendRecord) -> None:
    """Tear down the isolated runtime behind a pruned pool row.

    Dropping the row alone does not free capacity: the runtime stays registered
    with a live heartbeat, so it keeps counting against ``active_cap`` while no
    borrower can ever reach it again. Releasing it here is what actually returns
    the slot to the pool.
    """
    runtime_id = str(record.get("runtimeId") or "")
    owner_token = str(record.get("ownerToken") or "")
    if not runtime_id or not owner_token:
        return
    try:
        from isolated_runtime.reaper import release_runtime
    except ImportError:
        return
    try:
        release_runtime(runtime_id, owner_token)
    except (OSError, RuntimeError, ValueError) as exc:
        # Cleanup failure must not abort pool maintenance; the runtime reaper
        # still reclaims the record once its heartbeat lapses.
        print(
            f"E2E_SHPOIB_WARM_POOL_RELEASE_FAIL: runtime={runtime_id} detail={exc}",
            file=sys.stderr,
        )


def _borrower_still_alive(record: WarmBackendRecord) -> bool:
    """True when a borrowed row's owner process is still running.

    ``_record_is_stale`` already flags borrowed rows whose owner PID died, so a
    borrowed row only legitimately survives pruning while its borrower is alive
    (it releases the row via ``release_warm_backend``). A malformed/missing
    ``ownerPid`` is treated as dead so the row cannot pin capacity forever.
    """
    owner_pid = record.get("ownerPid")
    return isinstance(owner_pid, int) and _pid_alive(owner_pid)


def _prune_stale(registry: WarmPoolRegistry, *, now: float) -> int:
    removed = 0
    stale_keys: list[str] = []
    for key, record in registry["backends"].items():
        if _record_is_stale(record, now=now):
            stale_keys.append(key)
    for key in stale_keys:
        record = registry["backends"].pop(key, None)
        if record is None:
            continue
        removed += 1
        if record.get("state") == "borrowed" and _borrower_still_alive(record):
            # A live borrower owns this row and releases it via
            # release_warm_backend; the pool must not tear down a backend that
            # is currently serving an in-flight test.
            continue
        # Every other pruned row must actually free its isolated runtime.
        # Dropping the row alone leaves the runtime registered with a live
        # heartbeat, so it keeps counting against active_cap while no borrower
        # can ever reach it again — a leaked slot that stalls later PRIVATE
        # tests in ``E2E_SHPOIB_CAPACITY_WAIT``.
        _release_pruned_runtime(record)
    return removed


def _count_ready(registry: WarmPoolRegistry) -> int:
    count = 0
    for record in registry["backends"].values():
        if record.get("state") == "ready":
            count += 1
    return count


def try_borrow_warm_backend(
    *, borrower_pid: int | None = None
) -> WarmBorrowResult | None:
    """Borrow a ready warm backend for pytest SHPOIB bootstrap, if available."""
    if os.environ.get("MYRM_E2E_SHPOIB_WARM_POOL", "1").strip() in {"0", "false", "no"}:
        return None
    resolved_pid = borrower_pid if borrower_pid is not None else os.getpid()
    with _registry_lock():
        now = time.time()
        registry = _load_registry()
        _prune_stale(registry, now=now)
        workspace_fp = _workspace_source_fingerprint()
        for key, record in list(registry["backends"].items()):
            if record.get("state") != "ready":
                continue
            runtime_id = str(record.get("runtimeId", key))
            owner_token = record.get("ownerToken")
            api_base = record.get("apiBase")
            if not isinstance(owner_token, str) or not isinstance(api_base, str):
                registry["backends"].pop(key, None)
                continue
            if not warm_backend_health_ok(api_base, runtime_id):
                print(
                    "E2E_SHPOIB_WARM_POOL_PRUNE: "
                    f"runtime={runtime_id} api={api_base} reason=unhealthy",
                    file=sys.stderr,
                )
                registry["backends"].pop(key, None)
                continue
            # §26.26: never borrow a backend whose source differs from the
            # current workspace — it would run tests against stale code.
            # Records spawned by newer maintain already carry the fingerprint;
            # legacy rows (no fingerprint) are probed live.
            stored_fp = record.get("sourceFingerprint")
            if workspace_fp:
                if isinstance(stored_fp, str) and stored_fp:
                    backend_fp = stored_fp
                else:
                    backend_fp = warm_backend_source_fingerprint(api_base)
                if backend_fp and backend_fp != workspace_fp:
                    print(
                        "E2E_SHPOIB_WARM_POOL_STALE_CODE: "
                        f"runtime={runtime_id} api={api_base}",
                        file=sys.stderr,
                    )
                    registry["backends"].pop(key, None)
                    continue
            record["state"] = "borrowed"
            record["ownerPid"] = resolved_pid
            record["heartbeatAt"] = now
            _save_registry(registry)
            environment = {
                "E2E_API_BASE": api_base.rstrip("/"),
                "MYRM_E2E_PRIVATE_RUNTIME_ID": runtime_id,
                "MYRM_E2E_PRIVATE_BACKEND": "1",
                "MYRM_PRIVATE_BACKEND": "1",
                "MYRM_E2E_SHPOIB": "1",
                "MYRM_E2E_WARM_POOL_BORROW": "1",
                # Borrowed backends are warm-period seeded; the borrow
                # contract resets providers to the borrower's authoritative
                # env so a reused backend never serves a peer's seed (R2).
                "MYRM_E2E_FORCE_MODEL_SEED": "1",
            }
            print(
                f"E2E_SHPOIB_WARM_POOL_BORROW: runtime={runtime_id} api={api_base}",
                file=sys.stderr,
            )
            return WarmBorrowResult(
                ok=True,
                runtime_id=runtime_id,
                owner_token=owner_token,
                api_base=api_base.rstrip("/"),
                detail="borrowed",
                environment=environment,
            )
        # Persist pruned rows (unhealthy / stale-code backends removed during
        # this pass) even when nothing was borrowed, so the next maintain or
        # borrow does not re-probe them.
        _save_registry(registry)
        return None


def release_warm_backend(*, runtime_id: str) -> bool:
    """Drop borrowed backend from pool registry (backend reaper handles process)."""
    with _registry_lock():
        registry = _load_registry()
        removed = registry["backends"].pop(runtime_id, None) is not None
        _save_registry(registry)
        if removed:
            print(
                f"E2E_SHPOIB_WARM_POOL_RELEASE: runtime={runtime_id}",
                file=sys.stderr,
            )
        return removed


def warm_pool_snapshot() -> dict[str, object]:
    registry = _load_registry()
    _prune_stale(registry, now=time.time())
    ready = _count_ready(registry)
    borrowed = sum(
        1
        for record in registry["backends"].values()
        if record.get("state") == "borrowed"
    )
    return {
        "readyCount": ready,
        "borrowedCount": borrowed,
        "totalCount": len(registry["backends"]),
        "targetSize": DEFAULT_POOL_SIZE,
    }
