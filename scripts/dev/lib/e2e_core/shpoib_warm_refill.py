"""SHPOIB warm pool refill: boots backends that later PRIVATE lanes borrow (R159).

[INPUT] e2e_core.shpoib_warm_pool (registry, locks, prune), e2e_core.verify_backend_seed
[OUTPUT] maintain_warm_pool(), CLI ``maintain`` / ``status``
[POS] Dev Gate layer. A cold backend boot takes minutes, so the refill never holds the
registry lock while booting: borrowers keep getting their answer in milliseconds, and a
second refill returns at once instead of queueing behind the running one.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

# 作为脚本直接执行时（`python .../e2e_core/shpoib_warm_refill.py`），sys.path[0] 指向模块自身所在
# 目录而非 dev lib 根，导致模块级导入 e2e_core.* 失败；自举 dev lib 根，与 dev_gate/cli.py 同模式。
if __package__ in (None, ""):
    _lib_root = str(Path(__file__).resolve().parent.parent)
    if _lib_root not in sys.path:
        sys.path.insert(0, _lib_root)

from e2e_core.shpoib_warm_pool import (
    DEFAULT_POOL_SIZE,
    WarmBorrowResult,
    _count_ready,
    _load_registry,
    _pid_alive,
    _prune_stale,
    _refill_slot,
    _registry_lock,
    _save_registry,
    _workspace_source_fingerprint,
    warm_pool_snapshot,
)

_MAX_POOL_SIZE = 4


def _monorepo_root() -> Path:
    raw = os.environ.get("MYRM_MONOREPO_ROOT", "").strip()
    if raw:
        return Path(raw).resolve()
    return Path(__file__).resolve().parents[5]


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


def _spawn_and_publish(*, monorepo: Path) -> bool:
    """Boot one backend with the registry lock released, then publish its row.

    Returns False when the refill should stop (spawn failed or left no live backend).
    """
    result = _spawn_warm_backend(monorepo=monorepo)
    if not result.ok:
        print(
            f"E2E_SHPOIB_WARM_POOL_SPAWN_FAIL: {result.detail}",
            file=sys.stderr,
        )
        return False
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
        return False
    fingerprint = _workspace_source_fingerprint()
    with _registry_lock():
        registry = _load_registry()
        now = time.time()
        registry["backends"][result.runtime_id] = {
            "runtimeId": result.runtime_id,
            "ownerToken": result.owner_token,
            "apiBase": result.api_base,
            "state": "ready",
            "ownerPid": backend_pid,
            "heartbeatAt": now,
            "acquiredAt": now,
            "sourceFingerprint": fingerprint,
        }
        _save_registry(registry)
    print(
        f"E2E_SHPOIB_WARM_POOL_OK: runtime={result.runtime_id} api={result.api_base}",
        file=sys.stderr,
    )
    return True


def maintain_warm_pool(*, target_size: int | None = None) -> int:
    """Top up warm pool to target_size ready backends. Returns ready count.

    Single-flight: a second caller returns at once instead of queueing behind the
    running refill, which re-checks the deficit before every spawn.
    """
    monorepo = _monorepo_root()
    resolved_target = target_size
    if resolved_target is None:
        raw = os.environ.get("MYRM_E2E_SHPOIB_WARM_POOL_SIZE", "").strip()
        resolved_target = int(raw) if raw.isdigit() else DEFAULT_POOL_SIZE
    resolved_target = max(0, min(_MAX_POOL_SIZE, resolved_target))
    if resolved_target == 0:
        return 0
    if os.environ.get("MYRM_E2E_SHPOIB_WARM_POOL", "1").strip() in {"0", "false", "no"}:
        return 0

    with _refill_slot() as is_refiller:
        if not is_refiller:
            return _count_ready(_load_registry())
        for _ in range(resolved_target):
            with _registry_lock():
                registry = _load_registry()
                _prune_stale(registry, now=time.time())
                _save_registry(registry)
            if _count_ready(registry) >= resolved_target:
                break
            if not _spawn_and_publish(monorepo=monorepo):
                break
    return _count_ready(_load_registry())


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
        print(maintain_warm_pool(target_size=args.size))
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
