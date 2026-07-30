"""SHPOIB warm backend pool for LIVE chrome_e2e (R159).

[POS] Dev Gate layer. Keeps hot private backends ready for borrow to cut
cold bootstrap (~89s) to near-zero on pool hit. Pattern derived from
signoff_clarify_shpoib_pool.py (flock + registry + progress tokens).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypedDict

DEFAULT_POOL_SIZE: Final[int] = 2
POOL_PROGRESS_INTERVAL_SEC: Final[float] = 30.0
_SCHEMA_VERSION: Final[int] = 1


class WarmBackendRecord(TypedDict):
    runtimeId: str
    ownerToken: str
    apiBase: str
    state: str
    ownerPid: int
    heartbeatAt: float
    acquiredAt: float


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
    return Path(__file__).resolve().parents[4]


def _pool_root() -> Path:
    raw = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(raw) if raw else Path.home() / ".local/state/myrm-dev"
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


def _prune_stale(registry: WarmPoolRegistry, *, now: float) -> int:
    removed = 0
    stale_keys: list[str] = []
    for key, record in registry["backends"].items():
        owner_pid = record.get("ownerPid")
        heartbeat_at = record.get("heartbeatAt")
        state = record.get("state")
        if state == "borrowed":
            continue
        if not isinstance(owner_pid, int) or not isinstance(heartbeat_at, (int, float)):
            stale_keys.append(key)
            continue
        if not _pid_alive(owner_pid):
            stale_keys.append(key)
            continue
        if now - float(heartbeat_at) > 900.0:
            stale_keys.append(key)
    for key in stale_keys:
        registry["backends"].pop(key, None)
        removed += 1
    return removed


def _spawn_warm_backend(*, monorepo: Path) -> WarmBorrowResult:
    from verify_backend_seed import _spawn_verify_backend_seed  # noqa: PLC0415

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
                registry["backends"][key] = {
                    "runtimeId": result.runtime_id,
                    "ownerToken": result.owner_token,
                    "apiBase": result.api_base,
                    "state": "ready",
                    "ownerPid": os.getpid(),
                    "heartbeatAt": now,
                    "acquiredAt": now,
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
            for key, record in list(registry["backends"].items()):
                if record.get("state") != "ready":
                    continue
                runtime_id = str(record.get("runtimeId", key))
                owner_token = record.get("ownerToken")
                api_base = record.get("apiBase")
                if not isinstance(owner_token, str) or not isinstance(api_base, str):
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
