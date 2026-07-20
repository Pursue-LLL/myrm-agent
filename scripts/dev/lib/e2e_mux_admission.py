"""Global mux session admission for formal chrome_e2e (READ + LIVE lanes).

[POS] Registry-backed global cap on concurrent chrome_e2e mux sessions; complements
LIVE_AGENT lease cap with E2E_MUX_ADMISSION_WAIT backpressure (R17/R21).
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

SCHEMA_VERSION = 1
DEFAULT_OWNER_TTL_SEC = 900.0
DEFAULT_MAX_SESSIONS = 6
DEFAULT_WAIT_SEC = 900
DEFAULT_POLL_SEC = 15
SIGNOFF_MATRIX_PRIORITY = 10
NORMAL_PRIORITY = 0


class MuxAdmissionRecord(TypedDict):
    sessionId: str
    ownerPid: int
    runId: str
    lane: str
    priority: int
    ownerToken: str
    heartbeatAt: float
    acquiredAt: float
    signoffMatrix: NotRequired[bool]


class MuxAdmissionRegistry(TypedDict):
    schemaVersion: int
    sessions: dict[str, MuxAdmissionRecord]


def _dev_state_dir() -> Path:
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    return resolve_dev_state_dir()


def _state_root() -> Path:
    return _dev_state_dir() / "mux-admission"


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


def _load_registry(path: Path) -> MuxAdmissionRegistry:
    if not path.is_file():
        return {"schemaVersion": SCHEMA_VERSION, "sessions": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"schemaVersion": SCHEMA_VERSION, "sessions": {}}
    if not isinstance(payload, dict):
        return {"schemaVersion": SCHEMA_VERSION, "sessions": {}}
    sessions_raw = payload.get("sessions")
    sessions: dict[str, MuxAdmissionRecord] = {}
    if isinstance(sessions_raw, dict):
        for session_id, raw in sessions_raw.items():
            if isinstance(raw, dict) and isinstance(session_id, str):
                sessions[session_id] = raw  # type: ignore[assignment]
    return {"schemaVersion": SCHEMA_VERSION, "sessions": sessions}


def _save_registry(path: Path, registry: MuxAdmissionRegistry) -> None:
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(registry, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _prune_stale(registry: MuxAdmissionRegistry, *, now: float) -> int:
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
    """Stable registry key; accepts MYRM_E2E_RUN_ID labels or UUID strings."""
    try:
        return str(uuid.UUID(session_id))
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"myrm-mux-admission:{session_id}"))


def _session_priority(*, signoff_matrix: bool) -> int:
    return SIGNOFF_MATRIX_PRIORITY if signoff_matrix else NORMAL_PRIORITY


def effective_max_sessions(*, signoff_matrix: bool = False) -> int:
    """Return global mux session cap (signoff_matrix ignored — product uses full cap)."""
    _ = signoff_matrix
    base_raw = os.environ.get("MYRM_MUX_MAX_CONCURRENT_SESSIONS", str(DEFAULT_MAX_SESSIONS))
    try:
        return max(1, int(base_raw))
    except ValueError:
        return DEFAULT_MAX_SESSIONS


def _active_count(registry: MuxAdmissionRegistry) -> int:
    return len(registry["sessions"])


def try_acquire(
    *,
    session_id: str,
    run_id: str,
    lane: str,
    owner_pid: int,
    signoff_matrix: bool,
) -> tuple[bool, str | None, str]:
    """Return (ok, owner_token, reason). reason is ADMITTED | CAP_FULL."""
    registry_key = _registry_key(session_id)
    now = time.time()
    priority = _session_priority(signoff_matrix=signoff_matrix)
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
        cap = effective_max_sessions(signoff_matrix=signoff_matrix)
        if _active_count(registry) >= cap:
            _save_registry(registry_path, registry)
            return False, None, "CAP_FULL"
        token = secrets.token_hex(16)
        record: MuxAdmissionRecord = {
            "sessionId": session_id,
            "ownerPid": owner_pid,
            "runId": run_id,
            "lane": lane,
            "priority": priority,
            "ownerToken": token,
            "heartbeatAt": now,
            "acquiredAt": now,
        }
        if signoff_matrix:
            record["signoffMatrix"] = True
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


def heartbeat(*, session_id: str, owner_token: str) -> bool:
    registry_key = _registry_key(session_id)
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        record = registry["sessions"].get(registry_key)
        if not isinstance(record, dict):
            return False
        if record.get("ownerToken") != owner_token:
            return False
        record["heartbeatAt"] = now
        _save_registry(registry_path, registry)
        return True


def prune_stale() -> int:
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        removed = _prune_stale(registry, now=now)
        _save_registry(registry_path, registry)
        return removed


def _mux_registry_active_count() -> int:
    now = time.time()
    with _locked_registry() as registry_path:
        registry = _load_registry(registry_path)
        _prune_stale(registry, now=now)
        return _active_count(registry)


def acquire_with_wait(
    *,
    session_id: str,
    run_id: str,
    lane: str,
    owner_pid: int,
    signoff_matrix: bool,
) -> tuple[str, str]:
    from e2e_capacity_messages import format_mux_wait, format_mux_wait_timeout

    wait_sec = int(os.environ.get("MYRM_E2E_MUX_ADMISSION_WAIT_SEC", str(DEFAULT_WAIT_SEC)))
    poll_sec = int(os.environ.get("MYRM_E2E_MUX_ADMISSION_POLL_SEC", str(DEFAULT_POLL_SEC)))
    poll_sec = max(1, poll_sec)
    started = time.monotonic()
    while True:
        ok, token, reason = try_acquire(
            session_id=session_id,
            run_id=run_id,
            lane=lane,
            owner_pid=owner_pid,
            signoff_matrix=signoff_matrix,
        )
        if ok and token:
            cap = effective_max_sessions(signoff_matrix=signoff_matrix)
            print(
                f"E2E_MUX_ADMISSION_OK: session={session_id} lane={lane} cap={cap}",
                file=sys.stderr,
            )
            return token, reason
        elapsed = int(time.monotonic() - started)
        cap = effective_max_sessions(signoff_matrix=signoff_matrix)
        active = _mux_registry_active_count()
        if elapsed >= wait_sec:
            print(
                f"E2E_MUX_ADMISSION_WAIT_TIMEOUT: lane={lane} waited {wait_sec}s "
                f"(cap={cap})",
                file=sys.stderr,
            )
            print(
                format_mux_wait_timeout(lane=lane, wait_sec=wait_sec, cap=cap),
                file=sys.stderr,
            )
            raise SystemExit(3)
        print(
            f"E2E_MUX_ADMISSION_WAIT: lane={lane} mux busy — retry in {poll_sec}s "
            f"(elapsed={elapsed}s cap={cap})",
            file=sys.stderr,
        )
        print(
            format_mux_wait(
                lane=lane,
                elapsed_sec=elapsed,
                wait_sec=wait_sec,
                poll_sec=poll_sec,
                cap=cap,
                active=active,
            ),
            file=sys.stderr,
        )
        prune_stale()
        time.sleep(poll_sec)


def _parse_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Global mux admission for chrome_e2e")
    sub = parser.add_subparsers(dest="command", required=True)
    acquire = sub.add_parser("acquire")
    acquire.add_argument("--session-id", required=True)
    acquire.add_argument("--run-id", required=True)
    acquire.add_argument("--lane", required=True)
    acquire.add_argument("--owner-pid", type=int, default=os.getpid())
    acquire.add_argument("--signoff-matrix", default="0")
    acquire.add_argument("--wait", action="store_true")
    release = sub.add_parser("release")
    release.add_argument("--session-id", required=True)
    release.add_argument("--owner-token", required=True)
    heartbeat_cmd = sub.add_parser("heartbeat")
    heartbeat_cmd.add_argument("--session-id", required=True)
    heartbeat_cmd.add_argument("--owner-token", required=True)
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
            "maxSessions": effective_max_sessions(signoff_matrix=False),
            "sessions": list(registry["sessions"].keys()),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(
                f"mux-admission active={payload['active']} "
                f"max={payload['maxSessions']}"
            )
        return 0
    if args.command == "release":
        return 0 if release(session_id=args.session_id, owner_token=args.owner_token) else 1
    if args.command == "heartbeat":
        return 0 if heartbeat(session_id=args.session_id, owner_token=args.owner_token) else 1
    signoff_matrix = _parse_bool(args.signoff_matrix)
    if args.wait:
        token, _ = acquire_with_wait(
            session_id=args.session_id,
            run_id=args.run_id,
            lane=args.lane,
            owner_pid=args.owner_pid,
            signoff_matrix=signoff_matrix,
        )
        print(token)
        return 0
    ok, token, reason = try_acquire(
        session_id=args.session_id,
        run_id=args.run_id,
        lane=args.lane,
        owner_pid=args.owner_pid,
        signoff_matrix=signoff_matrix,
    )
    if not ok or not token:
        print(reason, file=sys.stderr)
        return 3
    print(token)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
