"""Chrome E2E pytest session dedupe — reject duplicate concurrent invocations (R32)."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import TypedDict


class _DedupeRecord(TypedDict):
    fingerprint: str
    holderPid: int
    parentPid: int
    argv: list[str]
    acquiredAt: float
    heartbeatAt: float


def _dev_state_dir() -> Path:
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    return resolve_dev_state_dir()


def _dedupe_root() -> Path:
    return _dev_state_dir() / "pytest-chrome-e2e-dedupe"


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


def _normalize_argv(argv: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    skip_next = False
    for index, arg in enumerate(argv):
        if skip_next:
            skip_next = False
            continue
        if arg in {"-n", "--numprocesses"}:
            skip_next = True
            continue
        if arg.startswith("MYRM_E2E_RUN_ID="):
            continue
        normalized.append(arg)
    return tuple(normalized)


def fingerprint_argv(argv: tuple[str, ...]) -> str:
    """Stable hash for chrome_e2e pytest argv (ignores ephemeral run ids)."""
    payload = "\0".join(_normalize_argv(argv)).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def _record_path(fingerprint: str) -> Path:
    return _dedupe_root() / f"{fingerprint}.json"


def _load_record(path: Path) -> _DedupeRecord | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload  # type: ignore[return-value]


def _max_holder_wall_sec() -> float:
    from dev_gate_contract import LIVE_SINGLE_TEST_WALL_CLOCK_SEC

    return float(LIVE_SINGLE_TEST_WALL_CLOCK_SEC)


def _record_is_stale(record: _DedupeRecord, *, now: float) -> bool:
    holder_pid = record.get("holderPid")
    if not isinstance(holder_pid, int):
        return True
    if not _pid_alive(holder_pid):
        return True
    acquired_at = record.get("acquiredAt")
    if isinstance(acquired_at, (int, float)) and now - float(acquired_at) > _max_holder_wall_sec():
        return True
    heartbeat_at = record.get("heartbeatAt")
    if isinstance(heartbeat_at, (int, float)) and now - float(heartbeat_at) > 7200.0:
        return True
    return False


def _prune_stale_records(root: Path) -> None:
    if not root.is_dir():
        return
    now = time.time()
    for path in root.glob("*.json"):
        record = _load_record(path)
        if record is None:
            path.unlink(missing_ok=True)
            continue
        if _record_is_stale(record, now=now):
            stale_pid = record.get("holderPid")
            print(
                f"E2E_PYTEST_DEDUPE_REAP: fingerprint={record.get('fingerprint')} "
                f"holder_pid={stale_pid} reason=stale",
                file=sys.stderr,
            )
            path.unlink(missing_ok=True)


def find_duplicate_pid(
    fingerprint: str,
    *,
    exclude_pids: tuple[int, ...] = (),
) -> int | None:
    root = _dedupe_root()
    _prune_stale_records(root)
    path = _record_path(fingerprint)
    record = _load_record(path)
    if record is None:
        return None
    holder_pid = record.get("holderPid")
    if not isinstance(holder_pid, int):
        return None
    if holder_pid in exclude_pids:
        return None
    if not _pid_alive(holder_pid):
        path.unlink(missing_ok=True)
        return None
    return holder_pid


def acquire_session_lock(
    fingerprint: str,
    *,
    argv: tuple[str, ...],
    holder_pid: int | None = None,
) -> None:
    resolved_pid = holder_pid if holder_pid is not None else os.getpid()
    root = _dedupe_root()
    root.mkdir(parents=True, exist_ok=True)
    _prune_stale_records(root)
    duplicate = find_duplicate_pid(fingerprint, exclude_pids=(resolved_pid, os.getppid()))
    if duplicate is not None:
        message = (
            f"E2E_PYTEST_DEDUPE_DENIED: duplicate chrome_e2e session "
            f"fingerprint={fingerprint} holder_pid={duplicate} — "
            "wait for the existing run or stop relaunching the same test"
        )
        print(message, file=sys.stderr)
        raise SystemExit(2)
    now = time.time()
    record: _DedupeRecord = {
        "fingerprint": fingerprint,
        "holderPid": resolved_pid,
        "parentPid": os.getppid(),
        "argv": list(_normalize_argv(argv)),
        "acquiredAt": now,
        "heartbeatAt": now,
    }
    path = _record_path(fingerprint)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def release_session_lock(fingerprint: str, *, holder_pid: int | None = None) -> None:
    resolved_pid = holder_pid if holder_pid is not None else os.getpid()
    path = _record_path(fingerprint)
    record = _load_record(path)
    if record is None:
        return
    if record.get("holderPid") != resolved_pid:
        return
    path.unlink(missing_ok=True)
