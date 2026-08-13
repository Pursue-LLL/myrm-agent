"""SHPOIB warm backend pool for LIVE chrome_e2e (R159).

[POS] Dev Gate layer. Keeps hot private backends ready for borrow to cut
cold bootstrap (~89s) to near-zero on pool hit. Pattern derived from flock + registry + progress tokens (R159).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Final, TypedDict

from e2e_core.real_user_home import real_user_home

DEFAULT_POOL_SIZE: Final[int] = 2
POOL_PROGRESS_INTERVAL_SEC: Final[float] = 30.0
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


def _monorepo_root() -> Path:
    raw = os.environ.get("MYRM_MONOREPO_ROOT", "").strip()
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[5]


def _pool_root() -> Path:
    raw = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(raw) if raw else real_user_home() / ".local/state/myrm-dev"
    return base / "shpoib-warm-pool"


def _registry_path() -> Path:
    return _pool_root() / "registry.json"


def _lock_path() -> Path:
    return _pool_root() / "registry.lock"


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
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
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


def _prune_stale(registry: WarmPoolRegistry, *, now: float) -> int:
    removed = 0
    stale_keys: list[str] = []
    for key, record in registry["backends"].items():
        if _record_is_stale(record, now=now):
            stale_keys.append(key)
    for key in stale_keys:
        registry["backends"].pop(key, None)
        removed += 1
    return removed


def _spawn_warm_backend(*, monorepo: Path) -> WarmBorrowResult:
    from e2e_core.verify_backend_seed import _spawn_verify_backend_seed

    spawned = _spawn_verify_backend_seed(monorepo=monorepo)
    if not spawned.ok:
        return WarmBorrowResult(
            ok=False,
            runtime_id=spawned.runtime_id,
            owner_token=spawned.owner_token,
            api_base=spawned.api_base,
            detail=spawned.detail,
            environment={},
        )
    owner_token = spawned.owner_token or f"warm-pool-{uuid.uuid4().hex[:12]}"
    environment = {
        "E2E_API_BASE": spawned.api_base.rstrip("/"),
        "MYRM_E2E_PRIVATE_RUNTIME_ID": spawned.runtime_id,
        "MYRM_E2E_PRIVATE_BACKEND": "1",
        "MYRM_PRIVATE_BACKEND": "1",
        "MYRM_E2E_SHPOIB": "1",
    }
    return WarmBorrowResult(
        ok=True,
        runtime_id=spawned.runtime_id,
        owner_token=owner_token,
        api_base=spawned.api_base.rstrip("/"),
        detail="spawned",
        environment=environment,
    )


def _backend_process_pid(runtime_id: str) -> int | None:
    """Read the detached backend PID, not the short-lived pool maintainer PID."""
    try:
        from isolated_runtime.allocator import get_runtime

        record = get_runtime(runtime_id)
    except (ImportError, OSError, RuntimeError, ValueError):
        return None
    identity = record.get("backendProcess")
    if not isinstance(identity, dict):
        return None
    pid = identity.get("pid")
    return pid if isinstance(pid, int) and pid > 0 else None


def _count_ready(registry: WarmPoolRegistry) -> int:
    count = 0
    for record in registry["backends"].values():
        if record.get("state") == "ready":
            count += 1
    return count


def maintain_warm_pool(*, target_size: int | None = None) -> int:
    """Top up warm pool to target_size ready backends. Returns ready count."""
    monorepo = _monorepo_root()
    resolved_target = target_size
    if resolved_target is None:
        raw = os.environ.get("MYRM_E2E_SHPOIB_WARM_POOL_SIZE", "").strip()
        resolved_target = int(raw) if raw.isdigit() else DEFAULT_POOL_SIZE
    resolved_target = max(0, min(4, resolved_target))
    if resolved_target == 0:
        return 0
    if os.environ.get("MYRM_E2E_SHPOIB_WARM_POOL", "1").strip() in {"0", "false", "no"}:
        return 0

    _pool_root().mkdir(parents=True, exist_ok=True)
    with _lock_path().open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            now = time.time()
            registry = _load_registry()
            _prune_stale(registry, now=now)
            ready = _count_ready(registry)
            spawned = 0
            while ready + spawned < resolved_target:
                result = _spawn_warm_backend(monorepo=monorepo)
                if not result.ok:
                    print(
                        f"E2E_SHPOIB_WARM_POOL_SPAWN_FAIL: {result.detail}",
                        file=sys.stderr,
                    )
                    break
                key = result.runtime_id
                backend_pid = _backend_process_pid(result.runtime_id)
                if backend_pid is None or not _pid_alive(backend_pid):
                    # Never publish a warm row owned by the short-lived
                    # `ready.sh` process; that row would be pruned immediately
                    # on the next borrow and hide a real pool failure.
                    try:
                        from isolated_runtime.reaper import release_runtime

                        release_runtime(result.runtime_id, result.owner_token)
                    except (ImportError, OSError, RuntimeError, ValueError):
                        pass
                    print(
                        "E2E_SHPOIB_WARM_POOL_SPAWN_FAIL: backend process identity missing",
                        file=sys.stderr,
                    )
                    break
                registry["backends"][key] = {
                    "runtimeId": result.runtime_id,
                    "ownerToken": result.owner_token,
                    "apiBase": result.api_base,
                    "state": "ready",
                    "ownerPid": backend_pid,
                    "heartbeatAt": now,
                    "acquiredAt": now,
                    "sourceFingerprint": _workspace_source_fingerprint(),
                }
                spawned += 1
                print(
                    f"E2E_SHPOIB_WARM_POOL_OK: runtime={result.runtime_id} "
                    f"api={result.api_base}",
                    file=sys.stderr,
                )
            _save_registry(registry)
            return _count_ready(registry)
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def try_borrow_warm_backend(*, borrower_pid: int | None = None) -> WarmBorrowResult | None:
    """Borrow a ready warm backend for pytest SHPOIB bootstrap, if available."""
    if os.environ.get("MYRM_E2E_SHPOIB_WARM_POOL", "1").strip() in {"0", "false", "no"}:
        return None
    resolved_pid = borrower_pid if borrower_pid is not None else os.getpid()
    _pool_root().mkdir(parents=True, exist_ok=True)
    with _lock_path().open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
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
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def release_warm_backend(*, runtime_id: str) -> bool:
    """Drop borrowed backend from pool registry (backend reaper handles process)."""
    with _lock_path().open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            registry = _load_registry()
            removed = registry["backends"].pop(runtime_id, None) is not None
            _save_registry(registry)
            if removed:
                print(
                    f"E2E_SHPOIB_WARM_POOL_RELEASE: runtime={runtime_id}",
                    file=sys.stderr,
                )
            return removed
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def warm_pool_snapshot() -> dict[str, object]:
    registry = _load_registry()
    _prune_stale(registry, now=time.time())
    ready = _count_ready(registry)
    borrowed = sum(
        1 for record in registry["backends"].values() if record.get("state") == "borrowed"
    )
    return {
        "readyCount": ready,
        "borrowedCount": borrowed,
        "totalCount": len(registry["backends"]),
        "targetSize": DEFAULT_POOL_SIZE,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SHPOIB warm backend pool (R159)")
    sub = parser.add_subparsers(dest="command", required=True)
    maintain = sub.add_parser("maintain")
    maintain.add_argument("--size", type=int, default=DEFAULT_POOL_SIZE)
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "maintain":
        count = maintain_warm_pool(target_size=args.size)
        print(count)
        return 0
    if args.command == "status":
        payload = warm_pool_snapshot()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                f"shpoib-warm-pool ready={payload['readyCount']} "
                f"borrowed={payload['borrowedCount']}"
            )
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
