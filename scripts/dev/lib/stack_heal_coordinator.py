"""StackHealCoordinator — single-writer shared backend heal (R145).

[INPUT]
- stack_mutation_policy.backend_heal_file_lock
- wave_active_lease_count / shared_api_http_ok

[OUTPUT]
- request_attach_crash_heal() -> exit code (0 deferred/skipped/ok, 1 failed)

[POS]
Dev Gate stack layer — serializes backend-only ensure across parallel ADMIT sessions.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Literal

StackHealAction = Literal[
    "NOOP_OK",
    "SKIPPED_SHPOIB",
    "SKIPPED_LEASES",
    "RUNNING",
    "DEFERRED",
    "FAILED",
]

_LEADER_PID_ENV = "MYRM_STACK_HEAL_LEADER_PID"


def _emit(action: StackHealAction, *, detail: str = "") -> None:
    suffix = f" {detail}" if detail else ""
    print(f"STACK_HEAL_{action}:{suffix}".rstrip(), file=sys.stderr, flush=True)


def request_attach_crash_heal(
    *,
    monorepo_root: Path,
    dev_stack: Path,
    lock_file: Path,
    wait_sec: float,
    shpoib: bool = False,
) -> int:
    from stack_mutation_policy import (  # noqa: PLC0415
        attach_backend_crash_heal_inner,
        backend_heal_file_lock,
        shared_api_http_ok,
    )

    if shared_api_http_ok():
        _emit("NOOP_OK")
        return 0

    shpoib_active = shpoib or os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"
    if shpoib_active:
        _emit(
            "SKIPPED_SHPOIB",
            detail="shared :8080 down — SHPOIB lane uses private backend; do not stop other pytest",
        )
        return 0

    try:
        with backend_heal_file_lock(lock_file, wait_sec):
            os.environ[_LEADER_PID_ENV] = str(os.getpid())
            _emit("RUNNING", detail=f"leader_pid={os.getpid()}")
            if shared_api_http_ok():
                _emit("NOOP_OK")
                return 0
            return attach_backend_crash_heal_inner(
                monorepo_root=monorepo_root,
                dev_stack=dev_stack,
            )
    except TimeoutError:
        leader = os.environ.get(_LEADER_PID_ENV, "?")
        _emit(
            "DEFERRED",
            detail=(
                f"flock busy after {wait_sec}s leader_hint={leader}; "
                "touch admit progress; do not stop other pytest"
            ),
        )
        _touch_admit_progress()
        return 0
    finally:
        os.environ.pop(_LEADER_PID_ENV, None)


def _touch_admit_progress() -> None:
    holder_raw = os.environ.get("MYRM_E2E_DEDUPE_HOLDER_PID", "").strip()
    if not holder_raw.isdigit():
        return
    from e2e_session_snapshot import touch_holder_session_progress  # noqa: PLC0415

    node = os.environ.get("E2E_ADMIT_NODE", "STACK_HEAL_DEFERRED")
    touch_holder_session_progress(holder_pid=int(holder_raw), current_node=node)


def coordinator_snapshot() -> dict[str, object]:
    leader = os.environ.get(_LEADER_PID_ENV, "").strip()
    return {
        "leaderPid": int(leader) if leader.isdigit() else None,
        "leaderEnv": _LEADER_PID_ENV,
    }


def _shpoib_lane_active(*, shpoib: bool) -> bool:
    return shpoib or os.environ.get("E2E_PROFILE_SHPOIB", "").strip() == "1"


def run_attach_health_preflight(
    *,
    monorepo_root: Path,
    dev_stack: Path,
    server_dir: Path,
    lock_file: Path,
    wait_sec: float,
    shpoib: bool = False,
) -> int:
    """R145 attach health probe — no shared-stack drift dogpile during parallel ADMIT.

    SHPOIB lanes never wait on shared :8080. Shared lanes use StackHealCoordinator
    only; pending drift apply runs exclusively when wave leases == 0.
    """
    from stack_mutation_policy import (  # noqa: PLC0415
        apply_pending_drift_if_idle,
        shared_api_http_ok,
        wave_active_lease_count,
    )

    if _shpoib_lane_active(shpoib=shpoib):
        _emit(
            "SKIPPED_SHPOIB",
            detail="attach health preflight uses private backend; shared :8080 ignored",
        )
        return 0

    if shared_api_http_ok():
        _emit("NOOP_OK", detail="shared api healthy")
        return 0

    rc = request_attach_crash_heal(
        monorepo_root=monorepo_root,
        dev_stack=dev_stack,
        lock_file=lock_file,
        wait_sec=wait_sec,
        shpoib=False,
    )
    if rc != 0:
        return rc
    if shared_api_http_ok():
        return 0

    active_leases = wave_active_lease_count(monorepo_root)
    if active_leases > 0:
        _emit(
            "SKIPPED_LEASES",
            detail=(
                f"shared api down; defer heal ({active_leases} active wave leases); "
                "preflight attach wait SSOT; do not stop other pytest"
            ),
        )
        return 1

    result = apply_pending_drift_if_idle(
        monorepo_root=monorepo_root,
        server_dir=server_dir,
    )
    if result.action == "failed":
        print(
            f"CHROME_E2E_FAIL: attach health pending drift apply failed: {result.detail}",
            file=sys.stderr,
            flush=True,
        )
        return 1
    if shared_api_http_ok():
        return 0
    print(
        "CHROME_E2E_ATTACH_HEALTH_PROBE_FAIL: shared api still down after idle drift apply",
        file=sys.stderr,
        flush=True,
    )
    return 1
