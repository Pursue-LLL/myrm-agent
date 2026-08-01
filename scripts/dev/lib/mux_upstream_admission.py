"""Global mux upstream cold-attach admission for chrome_e2e new_page (R22).

Registry-backed cap on concurrent mux cold attach operations across all pytest
sessions and MCP shims. Complements session-level ``e2e_mux_admission`` (R17).
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, TypedDict

from dev_gate_contract import (
    MUX_COLD_ATTACH_SLOTS,
    MUX_UPSTREAM_POLL_SEC,
    MUX_UPSTREAM_WAIT_SEC,
)

SCHEMA_VERSION = 1
DEFAULT_OWNER_TTL_SEC = 900.0
DEFAULT_COLD_ATTACH_HOLD_CAP_SEC = 120.0
DEFAULT_MAX_SLOTS = MUX_COLD_ATTACH_SLOTS
DEFAULT_WAIT_SEC = MUX_UPSTREAM_WAIT_SEC
DEFAULT_POLL_SEC = MUX_UPSTREAM_POLL_SEC


class UpstreamAdmissionRecord(TypedDict):
    operationId: str
    ownerPid: int
    ownerToken: str
    heartbeatAt: float
    acquiredAt: float


class UpstreamAdmissionRegistry(TypedDict):
    schemaVersion: int
    operations: dict[str, UpstreamAdmissionRecord]


def _dev_state_dir() -> Path:
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    return resolve_dev_state_dir()


def _state_root() -> Path:
    return _dev_state_dir() / "mux-upstream-admission"


@contextmanager
def _locked_registry() -> Iterator[Path]:
    root = _state_root()
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / "registry.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield root / "registry.json"
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


def _load_registry(path: Path) -> UpstreamAdmissionRegistry:
    if not path.is_file():
        return {"schemaVersion": SCHEMA_VERSION, "operations": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schemaVersion": SCHEMA_VERSION, "operations": {}}
    if not isinstance(payload, dict):
        return {"schemaVersion": SCHEMA_VERSION, "operations": {}}
    operations_raw = payload.get("operations")
    operations: dict[str, UpstreamAdmissionRecord] = {}
    if isinstance(operations_raw, dict):
        for operation_id, raw in operations_raw.items():
            if isinstance(raw, dict) and isinstance(operation_id, str):
                operations[operation_id] = raw  # type: ignore[assignment]
    return {"schemaVersion": SCHEMA_VERSION, "operations": operations}


def _save_registry(path: Path, registry: UpstreamAdmissionRegistry) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _owner_ttl_sec() -> float:
    return DEFAULT_OWNER_TTL_SEC


def _cold_attach_hold_cap_sec() -> float:
    raw = os.environ.get(
        "MYRM_MUX_COLD_ATTACH_HOLD_CAP_SEC",
        str(DEFAULT_COLD_ATTACH_HOLD_CAP_SEC),
    ).strip()
    try:
        return max(30.0, float(raw))
    except ValueError:
        return DEFAULT_COLD_ATTACH_HOLD_CAP_SEC


def _prune_stale(registry: UpstreamAdmissionRegistry, *, now: float) -> int:
    removed = 0
    operations = registry["operations"]
    stale_ids: list[str] = []
    hold_cap = _cold_attach_hold_cap_sec()
    owner_ttl = _owner_ttl_sec()
    for operation_id, record in operations.items():
        owner_pid = record.get("ownerPid")
        heartbeat_at = record.get("heartbeatAt")
        acquired_at = record.get("acquiredAt")
        if not isinstance(owner_pid, int) or not isinstance(heartbeat_at, (int, float)):
            stale_ids.append(operation_id)
            continue
        if not _pid_alive(owner_pid):
            stale_ids.append(operation_id)
            continue
        if now - float(heartbeat_at) > owner_ttl:
            stale_ids.append(operation_id)
            continue
        if (
            isinstance(acquired_at, (int, float))
            and now - float(acquired_at) > hold_cap
        ):
            stale_ids.append(operation_id)
            continue
    for operation_id in stale_ids:
        operations.pop(operation_id, None)
        removed += 1
    return removed


def _registry_key(operation_id: str) -> str:
    try:
        return str(uuid.UUID(operation_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"myrm-mux-upstream:{operation_id}"))


def effective_max_slots() -> int:
    """P0-B/P1: cold-attach slots follow Host Resource Governor effective cap."""
    try:
        from host_resource_governor import effective_browser_operation_credits

        cap = effective_browser_operation_credits()
    except ImportError:
        try:
            from browser_orchestrator import MAX_OPERATION_CREDITS

            cap = MAX_OPERATION_CREDITS
        except ImportError:
            cap = DEFAULT_MAX_SLOTS
    raw = os.environ.get("MYRM_MUX_COLD_ATTACH_SLOTS", "").strip()
    if raw:
        try:
            cap = min(cap, max(1, int(raw)))
        except ValueError:
            pass
    return cap


def _active_count(registry: UpstreamAdmissionRegistry) -> int:
    return len(registry["operations"])


def _admission_disabled() -> bool:
    return os.environ.get("MYRM_MUX_UPSTREAM_ADMISSION", "1").strip().lower() in {
        "0",
        "false",
        "no",
        "off",
    }


class MuxColdAttachStatus(TypedDict):
    active: int
    maxSlots: int
    saturated: bool
    handProbeAllowed: bool


@dataclass(frozen=True, slots=True)
class ActiveUpstreamOperation:
    operation_id: str
    owner_pid: int
    acquired_at: float


def list_active_upstream_operations() -> tuple[ActiveUpstreamOperation, ...]:
    """Durable mux operation credits (orchestrator SSOT); replaces process-scan TQ."""
    if _admission_disabled():
        return ()
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        _prune_stale(registry, now=now)
        active: list[ActiveUpstreamOperation] = []
        for operation_id, record in registry["operations"].items():
            if not isinstance(record, dict):
                continue
            owner_pid = record.get("ownerPid")
            acquired = record.get("acquiredAt")
            if not isinstance(owner_pid, int) or not isinstance(acquired, (int, float)):
                continue
            if not _pid_alive(owner_pid):
                continue
            active.append(
                ActiveUpstreamOperation(
                    operation_id=str(record.get("operationId", operation_id)),
                    owner_pid=owner_pid,
                    acquired_at=float(acquired),
                )
            )
        active.sort(key=lambda item: (item.owner_pid, item.operation_id))
        return tuple(active)


def read_mux_cold_attach_status() -> MuxColdAttachStatus:
    """Snapshot for Agent e2e-context: hand MCP new_page when not saturated."""
    cap = effective_max_slots()
    if _admission_disabled():
        return {
            "active": 0,
            "maxSlots": cap,
            "saturated": False,
            "handProbeAllowed": True,
        }
    prune_stale()
    active, resolved_cap = _active_snapshot()
    saturated = active >= resolved_cap
    peers = _parallel_mux_peer_count()
    parallel_headroom = _parallel_cold_attach_headroom(peers)
    hand_allowed = active + parallel_headroom <= resolved_cap
    return {
        "active": active,
        "maxSlots": resolved_cap,
        "saturated": saturated,
        "handProbeAllowed": hand_allowed and not saturated,
    }


def _parallel_mux_peer_count() -> int:
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load(force=True)
        return max(0, load.wave_leases, load.mux_contexts)
    except (ImportError, OSError, TypeError, ValueError):
        return 0


def _parallel_cold_attach_headroom(peers: int) -> int:
    """Reserve mux cold-attach slots under parallel wave/pytest load (R113)."""
    if peers <= 1:
        return 0
    cap = effective_max_slots()
    return min(max(1, cap - 1), max(1, peers - 1))


def wait_mux_hand_probe_allowed(*, budget_sec: float | None = None) -> None:
    """Wait for mux operation credit via Browser Orchestrator (P0-B SSOT)."""
    from browser_orchestrator import wait_for_operation_credit
    from transport_supervisor import mux_upstream_wait_cap

    wait_budget = float(
        budget_sec if budget_sec is not None else mux_upstream_wait_cap()
    )
    wait_for_operation_credit(
        budget_sec=wait_budget,
        current_node="mux_hand_probe_wait",
    )


def _active_snapshot() -> tuple[int, int]:
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        _prune_stale(registry, now=now)
        cap = effective_max_slots()
        return _active_count(registry), cap


def try_acquire(
    *,
    operation_id: str,
    owner_pid: int,
) -> tuple[bool, str | None, str]:
    """Return (ok, owner_token, reason). reason is ADMITTED | CAP_FULL."""
    if _admission_disabled():
        return True, "", "ADMITTED"
    registry_key = _registry_key(operation_id)
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        _prune_stale(registry, now=now)
        existing = registry["operations"].get(registry_key)
        if isinstance(existing, dict):
            token = existing.get("ownerToken")
            existing_pid = existing.get("ownerPid")
            if (
                isinstance(token, str)
                and token
                and isinstance(existing_pid, int)
                and existing_pid == owner_pid
            ):
                existing["heartbeatAt"] = now
                _save_registry(registry_path, registry)
                return True, token, "ADMITTED"
        cap = effective_max_slots()
        if _active_count(registry) >= cap:
            _save_registry(registry_path, registry)
            return False, None, "CAP_FULL"
        token = secrets.token_hex(16)
        record: UpstreamAdmissionRecord = {
            "operationId": operation_id,
            "ownerPid": owner_pid,
            "ownerToken": token,
            "heartbeatAt": now,
            "acquiredAt": now,
        }
        registry["operations"][registry_key] = record
        _save_registry(registry_path, registry)
        return True, token, "ADMITTED"


def release(*, operation_id: str, owner_token: str) -> bool:
    if _admission_disabled():
        return True
    registry_key = _registry_key(operation_id)
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        record = registry["operations"].get(registry_key)
        if not isinstance(record, dict):
            return True
        token = record.get("ownerToken")
        if token != owner_token:
            return False
        registry["operations"].pop(registry_key, None)
        _save_registry(registry_path, registry)
        return True


def prune_stale() -> int:
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        removed = _prune_stale(registry, now=now)
        _save_registry(registry_path, registry)
        return removed


def acquire_with_wait(
    *,
    operation_id: str,
    owner_pid: int,
) -> str:
    if _admission_disabled():
        return ""
    from transport_supervisor import mux_upstream_wait_cap

    env_wait = os.environ.get("MYRM_MUX_UPSTREAM_WAIT_SEC", "").strip()
    wait_sec = int(env_wait) if env_wait else mux_upstream_wait_cap()
    poll_sec = int(os.environ.get("MYRM_MUX_UPSTREAM_POLL_SEC", str(DEFAULT_POLL_SEC)))
    poll_sec = max(1, poll_sec)
    started = time.monotonic()
    while True:
        ok, token, _reason = try_acquire(operation_id=operation_id, owner_pid=owner_pid)
        if ok and token is not None:
            cap = effective_max_slots()
            print(
                f"MUX_UPSTREAM_OK: operation={operation_id} cap={cap}",
                file=sys.stderr,
            )
            return token
        elapsed = int(time.monotonic() - started)
        if elapsed >= wait_sec:
            cap = effective_max_slots()
            message = (
                f"MUX_UPSTREAM_WAIT_TIMEOUT: operation={operation_id} waited {wait_sec}s "
                f"(cap={cap})"
            )
            print(message, file=sys.stderr)
            raise RuntimeError(message)
        active, cap = _active_snapshot()
        pos = max(1, active - cap + 1)
        print(
            f"MUX_QUEUE_WAIT: operation={operation_id} pos={pos} active={active} cap={cap} "
            f"elapsed={elapsed}s — retry in {poll_sec}s (do not stop other tests)",
            file=sys.stderr,
        )
        print(
            f"MUX_UPSTREAM_WAIT: operation={operation_id} upstream busy — retry in {poll_sec}s "
            f"(elapsed={elapsed}s cap={cap})",
            file=sys.stderr,
        )
        try:
            from e2e_session_snapshot import touch_session_progress

            touch_session_progress()
        except ImportError:
            pass
        try:
            from e2e_session_lifecycle import touch_wall_progress

            touch_wall_progress(current_node="parallel_mux_upstream_wait")
        except ImportError:
            pass
        try:
            from e2e_lease_heartbeat import heartbeat_e2e_lease

            heartbeat_e2e_lease()
        except ImportError:
            pass
        prune_stale()
        time.sleep(poll_sec)


@contextmanager
def upstream_cold_attach_slot(*, operation_id: str | None = None) -> Iterator[str]:
    """Acquire a global mux upstream cold-attach slot for the duration of new_page."""
    resolved_operation_id = operation_id or str(uuid.uuid4())
    token = acquire_with_wait(operation_id=resolved_operation_id, owner_pid=os.getpid())
    try:
        yield resolved_operation_id
    finally:
        release(operation_id=resolved_operation_id, owner_token=token)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Global mux upstream cold-attach admission"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--operation-id", required=True)
    acquire.add_argument("--owner-pid", type=int, default=os.getpid())
    acquire.add_argument("--wait", action="store_true")
    release_cmd = sub.add_parser("release")
    release_cmd.add_argument("--operation-id", required=True)
    release_cmd.add_argument("--owner-token", required=True)
    sub.add_parser("prune")
    status = sub.add_parser("status")
    status.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "prune":
        print(prune_stale())
        return 0
    if args.command == "status":
        path = _state_root() / "registry.json"
        registry = _load_registry(path)
        _prune_stale(registry, now=time.time())
        payload = {
            "active": _active_count(registry),
            "maxSlots": effective_max_slots(),
            "operations": list(registry["operations"].keys()),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                f"mux-upstream-admission active={payload['active']} "
                f"max={payload['maxSlots']}"
            )
        return 0
    if args.command == "release":
        return (
            0
            if release(operation_id=args.operation_id, owner_token=args.owner_token)
            else 1
        )
    if args.wait:
        token = acquire_with_wait(
            operation_id=args.operation_id, owner_pid=args.owner_pid
        )
        print(token)
        return 0
    ok, token, reason = try_acquire(
        operation_id=args.operation_id, owner_pid=args.owner_pid
    )
    if not ok or token is None:
        print(reason, file=sys.stderr)
        return 3
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
