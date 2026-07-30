"""Global wave expensive-session admission for formal chrome_e2e (R158 ECC).

[POS] Early capacity claim at test.sh dedupe — before ADMIT shell spawn.
Complements mux-admission (handoff after mux OK) and isolated_runtime bootstrap caps.
READ lane weight=0 (mux-only); LIVE_AGENT weight=1.
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
from pathlib import Path
from typing import Iterator, NotRequired, TypedDict

from dev_gate_contract import (
    E2E_ADMISSION_WALL_CLOCK_SEC,
    WAVE_EXPENSIVE_SESSION_SLOTS,
)

SCHEMA_VERSION = 1
DEFAULT_OWNER_TTL_SEC = 900.0
DEFAULT_POLL_SEC = 15
ENV_WAVE_CAPACITY_TOKEN: str = "MYRM_E2E_WAVE_CAPACITY_TOKEN"
ENV_WAVE_CAPACITY_SESSION: str = "MYRM_E2E_WAVE_CAPACITY_SESSION"


class WaveCapacityRecord(TypedDict):
    sessionId: str
    ownerPid: int
    lane: str
    weight: int
    ownerToken: str
    heartbeatAt: float
    acquiredAt: float


class WaveCapacityRegistry(TypedDict):
    schemaVersion: int
    sessions: dict[str, WaveCapacityRecord]


def _dev_state_dir() -> Path:
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    return resolve_dev_state_dir()


def _state_root() -> Path:
    return _dev_state_dir() / "wave-capacity"


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


def _load_registry(path: Path) -> WaveCapacityRegistry:
    if not path.is_file():
        return {"schemaVersion": SCHEMA_VERSION, "sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schemaVersion": SCHEMA_VERSION, "sessions": {}}
    if not isinstance(payload, dict):
        return {"schemaVersion": SCHEMA_VERSION, "sessions": {}}
    sessions_raw = payload.get("sessions")
    sessions: dict[str, WaveCapacityRecord] = {}
    if isinstance(sessions_raw, dict):
        for session_id, raw in sessions_raw.items():
            if isinstance(raw, dict) and isinstance(session_id, str):
                sessions[session_id] = raw  # type: ignore[assignment]
    return {"schemaVersion": SCHEMA_VERSION, "sessions": sessions}


def _save_registry(path: Path, registry: WaveCapacityRegistry) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _prune_stale(registry: WaveCapacityRegistry, *, now: float) -> int:
    removed = 0
    sessions = registry["sessions"]
    stale_ids: list[str] = []
    for session_id, record in sessions.items():
        owner_pid = record.get("ownerPid")
        heartbeat_at = record.get("heartbeatAt")
        if not isinstance(owner_pid, int) or not isinstance(heartbeat_at, (int, float)):
            stale_ids.append(session_id)
            continue
        if not _pid_alive(owner_pid):
            stale_ids.append(session_id)
            continue
        if now - float(heartbeat_at) > DEFAULT_OWNER_TTL_SEC:
            stale_ids.append(session_id)
    for session_id in stale_ids:
        sessions.pop(session_id, None)
        removed += 1
    return removed


def _registry_key(session_id: str) -> str:
    try:
        return str(uuid.UUID(session_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"myrm-wave-capacity:{session_id}"))


def effective_expensive_slots() -> int:
    """Global expensive-session cap (SSOT aligned with mux cold attach per cell)."""
    try:
        from e2e_transport_cell import effective_expensive_session_slots

        return effective_expensive_session_slots()
    except ImportError:
        pass
    base_raw = os.environ.get(
        "MYRM_WAVE_EXPENSIVE_SESSION_SLOTS", str(WAVE_EXPENSIVE_SESSION_SLOTS)
    )
    try:
        return max(1, int(base_raw))
    except ValueError:
        return WAVE_EXPENSIVE_SESSION_SLOTS


def lane_expensive_weight(lane: str) -> int:
    """READ uses mux-only path; LIVE_AGENT consumes an expensive slot."""
    normalized = lane.strip().upper()
    if normalized == "READ":
        return 0
    return 1


def _active_weight(registry: WaveCapacityRegistry) -> int:
    total = 0
    for record in registry["sessions"].values():
        weight = record.get("weight")
        if isinstance(weight, int) and weight > 0:
            total += weight
    return total


def _resolve_wait_sec() -> int:
    raw = os.environ.get("MYRM_E2E_WAVE_CAPACITY_WAIT_SEC", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    return E2E_ADMISSION_WALL_CLOCK_SEC


def _resolve_poll_sec() -> int:
    raw = os.environ.get("MYRM_E2E_WAVE_CAPACITY_POLL_SEC", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return max(1, int(raw))
    return max(1, DEFAULT_POLL_SEC)


def try_acquire(
    *,
    session_id: str,
    lane: str,
    owner_pid: int,
) -> tuple[bool, str | None, str]:
    weight = lane_expensive_weight(lane)
    if weight == 0:
        token = secrets.token_hex(8)
        return True, token, "READ_FAST_PATH"

    registry_key = _registry_key(session_id)
    now = time.time()
    cap = effective_expensive_slots()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        _prune_stale(registry, now=now)
        existing = registry["sessions"].get(registry_key)
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
        if _active_weight(registry) + weight > cap:
            _save_registry(registry_path, registry)
            return False, None, "CAP_FULL"
        token = secrets.token_hex(16)
        record: WaveCapacityRecord = {
            "sessionId": session_id,
            "ownerPid": owner_pid,
            "lane": lane,
            "weight": weight,
            "ownerToken": token,
            "heartbeatAt": now,
            "acquiredAt": now,
        }
        registry["sessions"][registry_key] = record
        _save_registry(registry_path, registry)
        return True, token, "ADMITTED"


def release(*, session_id: str, owner_token: str) -> bool:
    registry_key = _registry_key(session_id)
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        record = registry["sessions"].get(registry_key)
        if not isinstance(record, dict):
            return True
        token = record.get("ownerToken")
        if token != owner_token:
            return False
        registry["sessions"].pop(registry_key, None)
        _save_registry(registry_path, registry)
        return True


def prune_stale() -> int:
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        removed = _prune_stale(registry, now=now)
        _save_registry(registry_path, registry)
        return removed


def capacity_snapshot() -> dict[str, object]:
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        _prune_stale(registry, now=now)
        active = _active_weight(registry)
        cap = effective_expensive_slots()
        return {
            "activeWeight": active,
            "maxSlots": cap,
            "saturated": active >= cap,
            "sessionCount": len(registry["sessions"]),
        }


def _touch_holder_progress(node: str) -> None:
    holder_raw = os.environ.get("MYRM_E2E_DEDUPE_HOLDER_PID", "").strip()
    if not holder_raw.isdigit():
        return
    from e2e_session_snapshot import touch_holder_session_progress  # noqa: PLC0415

    touch_holder_session_progress(holder_pid=int(holder_raw), current_node=node)


def acquire_with_wait(
    *,
    session_id: str,
    lane: str,
    owner_pid: int,
) -> tuple[str, str]:
    weight = lane_expensive_weight(lane)
    if weight == 0:
        token = f"read-{secrets.token_hex(8)}"
        print(
            f"E2E_WAVE_CAPACITY_OK: lane={lane} read_fast_path=1",
            file=sys.stderr,
        )
        return token, "READ_FAST_PATH"

    wait_sec = _resolve_wait_sec()
    poll_sec = _resolve_poll_sec()
    cap = effective_expensive_slots()
    started = time.monotonic()
    while True:
        ok, token, reason = try_acquire(
            session_id=session_id,
            lane=lane,
            owner_pid=owner_pid,
        )
        if ok and token:
            print(
                f"E2E_WAVE_CAPACITY_OK: session={session_id} lane={lane} "
                f"cap={cap} reason={reason}",
                file=sys.stderr,
            )
            return token, reason
        elapsed = int(time.monotonic() - started)
        snap = capacity_snapshot()
        active = snap.get("activeWeight", cap)
        if elapsed >= wait_sec:
            print(
                f"E2E_WAVE_CAPACITY_WAIT_TIMEOUT: lane={lane} waited {wait_sec}s "
                f"(cap={cap} active={active})",
                file=sys.stderr,
            )
            raise SystemExit(3)
        print(
            f"E2E_WAVE_CAPACITY_WAIT: lane={lane} busy — retry in {poll_sec}s "
            f"(elapsed={elapsed}s cap={cap} active={active})",
            file=sys.stderr,
        )
        _touch_holder_progress("E2E_WAVE_CAPACITY_WAIT")
        prune_stale()
        time.sleep(poll_sec)


def release_from_env() -> None:
    session_id = os.environ.get(ENV_WAVE_CAPACITY_SESSION, "").strip()
    token = os.environ.get(ENV_WAVE_CAPACITY_TOKEN, "").strip()
    if not session_id or not token:
        return
    release(session_id=session_id, owner_token=token)
    os.environ.pop(ENV_WAVE_CAPACITY_TOKEN, None)
    os.environ.pop(ENV_WAVE_CAPACITY_SESSION, None)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Wave expensive-session capacity (R158)")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--session-id", required=True)
    acquire.add_argument("--lane", required=True)
    acquire.add_argument("--owner-pid", type=int, default=os.getpid())
    acquire.add_argument("--wait", action="store_true")
    release_cmd = sub.add_parser("release")
    release_cmd.add_argument("--session-id", required=True)
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
        payload = capacity_snapshot()
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                f"wave-capacity active={payload['activeWeight']} "
                f"max={payload['maxSlots']} saturated={payload['saturated']}"
            )
        return 0
    if args.command == "release":
        return (
            0
            if release(session_id=args.session_id, owner_token=args.owner_token)
            else 1
        )
    if args.wait:
        token, _ = acquire_with_wait(
            session_id=args.session_id,
            lane=args.lane,
            owner_pid=args.owner_pid,
        )
        print(token)
        return 0
    ok, token, reason = try_acquire(
        session_id=args.session_id,
        lane=args.lane,
        owner_pid=args.owner_pid,
    )
    if not ok or not token:
        print(reason, file=sys.stderr)
        return 3
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
