"""Chrome E2E pytest session idempotency — one concurrent holder per submission key.

Rejects duplicate chrome_e2e relaunches that reuse the same ``MYRM_E2E_RUN_ID``
(or legacy argv fingerprint when run id is unavailable). Different submissions
may target the same ``tests/e2e/*.py`` file or node in parallel.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import fcntl
from pathlib import Path
from typing import TypedDict


class _DedupeRecord(TypedDict, total=False):
    fingerprint: str
    holderPid: int
    parentPid: int
    argv: list[str]
    acquiredAt: float
    heartbeatAt: float
    lane: str


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
    cosmetic_flags = frozenset(
        {"-q", "-v", "-s", "-x", "--quiet", "--verbose", "--capture=no"}
    )
    for arg in argv:
        if skip_next:
            skip_next = False
            continue
        if arg in {"-n", "--numprocesses"}:
            skip_next = True
            continue
        if arg.startswith("MYRM_E2E_RUN_ID="):
            continue
        if arg in cosmetic_flags:
            continue
        if arg.startswith(("-n", "--numprocesses=")):
            continue
        if arg.startswith(("--tb=", "--timeout=", "-k=")):
            continue
        normalized.append(arg)
    return tuple(normalized)


def e2e_file_scope_key(argv: tuple[str, ...]) -> str | None:
    """Normalized tests/e2e/*.py for any chrome_e2e invocation (whole-file or ::node)."""
    joined = " ".join(_normalize_argv(argv))
    if "-m" not in joined or "chrome_e2e" not in joined:
        return None
    import re

    match = re.search(
        r"((?:myrm-agent/myrm-agent-server/)?tests/e2e/[^\s:]+\.py)",
        joined,
    )
    if match is None:
        return None
    path = match.group(1)
    if path.startswith("myrm-agent/myrm-agent-server/"):
        path = path.removeprefix("myrm-agent/myrm-agent-server/")
    return path


def file_batch_key(argv: tuple[str, ...]) -> str | None:
    """Normalized tests/e2e/*.py path when invoked as whole-file batch (no ::node)."""
    if "::" in " ".join(_normalize_argv(argv)):
        return None
    return e2e_file_scope_key(argv)


def _file_batch_root() -> Path:
    return _dev_state_dir() / "pytest-chrome-e2e-file-batch"


def _is_guardrail_file_scope(scope_key: str | None) -> bool:
    return bool(scope_key and "test_guardrail_bash_chrome_e2e.py" in scope_key)


def _file_scope_bootstrap_stall_sec(scope_key: str | None = None) -> float:
    """Max bootstrap-only hold before file-scope lock is reapable (R276).

    Guardrail PRIVATE SHPOIB can sit in ADMIT/bootstrap >180s before pytest spawns;
    use PRIVATE ADMIT cap (900s) so duplicate whole-file guardrail cannot slip in.
    """
    if _is_guardrail_file_scope(scope_key):
        return 900.0
    return 180.0


def _holder_process_tree_has_pytest(holder_pid: int) -> bool:
    """True when holder's process tree includes a pytest invocation."""
    try:
        import subprocess

        holder_cmd = subprocess.run(
            ["ps", "-o", "command=", "-p", str(holder_pid)],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        holder_command = holder_cmd.stdout.strip()
        if "run_pytest_safe" in holder_command:
            return True

        proc = subprocess.run(
            ["pgrep", "-P", str(holder_pid)],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        child_pids = [
            int(token) for token in proc.stdout.split() if token.strip().isdigit()
        ]
    except (OSError, subprocess.TimeoutExpired, ValueError):
        child_pids = []
    stack = list(child_pids)
    seen: set[int] = set()
    while stack:
        pid = stack.pop()
        if pid in seen or pid <= 0:
            continue
        seen.add(pid)
        try:
            cmd = subprocess.run(
                ["ps", "-o", "command=", "-p", str(pid)],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        command = cmd.stdout.strip()
        if "run_pytest_safe" in command:
            return True
        if "pytest" in command and "chrome_e2e" in command:
            return True
        try:
            child_proc = subprocess.run(
                ["pgrep", "-P", str(pid)],
                capture_output=True,
                text=True,
                timeout=2.0,
                check=False,
            )
            stack.extend(
                int(token)
                for token in child_proc.stdout.split()
                if token.strip().isdigit()
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            continue
    return False


def _file_scope_record_is_stale(record: _DedupeRecord, *, now: float) -> bool:
    if _record_is_stale(record, now=now):
        return True
    holder_pid = record.get("holderPid")
    if not isinstance(holder_pid, int) or not _pid_alive(holder_pid):
        return True
    acquired_at = record.get("acquiredAt")
    if not isinstance(acquired_at, (int, float)):
        return True
    held_sec = now - float(acquired_at)
    scope_key = str(record.get("fingerprint", "")).strip() or None
    if held_sec <= _file_scope_bootstrap_stall_sec(scope_key):
        return False
    if _holder_process_tree_has_pytest(holder_pid):
        if _is_guardrail_file_scope(scope_key):
            try:
                from dev_gate_contract import _parallel_chrome_e2e_pressure
                from e2e_stale_lease_reap import _private_credit_queue_has_waiters

                if (
                    _parallel_chrome_e2e_pressure() >= 2
                    and _private_credit_queue_has_waiters()
                    and held_sec >= 300.0
                ):
                    return True
            except ImportError:
                pass
        return False
    return True


def _prune_stale_file_batch_records(root: Path) -> None:
    if not root.is_dir():
        return
    now = time.time()
    for path in root.glob("*.json"):
        if path.name == ".claim.lock":
            continue
        record = _load_record(path)
        if record is None:
            path.unlink(missing_ok=True)
            continue
        if _file_scope_record_is_stale(record, now=now):
            stale_pid = record.get("holderPid")
            print(
                f"E2E_FILE_SCOPE_DEDUPE_REAP: scope_key={record.get('fingerprint')} "
                f"holder_pid={stale_pid} reason=bootstrap_stall",
                file=sys.stderr,
            )
            path.unlink(missing_ok=True)


def _file_batch_record_path(batch_key: str) -> Path:
    digest = hashlib.sha256(batch_key.encode("utf-8")).hexdigest()[:16]
    return _file_batch_root() / f"{digest}.json"


def find_file_batch_duplicate(
    batch_key: str, *, exclude_pids: tuple[int, ...] = ()
) -> int | None:
    root = _file_batch_root()
    if not batch_key.strip():
        return None
    _prune_stale_file_batch_records(root)
    path = _file_batch_record_path(batch_key)
    record = _load_record(path)
    if record is None:
        return None
    holder_pid = record.get("holderPid")
    if not isinstance(holder_pid, int):
        path.unlink(missing_ok=True)
        return None
    if holder_pid in exclude_pids:
        return None
    if not _pid_alive(holder_pid):
        path.unlink(missing_ok=True)
        return None
    now = time.time()
    if _record_is_stale(record, now=now):
        path.unlink(missing_ok=True)
        return None
    return holder_pid


def find_file_scope_duplicate(
    scope_key: str, *, exclude_pids: tuple[int, ...] = ()
) -> int | None:
    """Return live holder pid for the same tests/e2e/*.py scope, if any."""
    return find_file_batch_duplicate(scope_key, exclude_pids=exclude_pids)


def fingerprint_argv(argv: tuple[str, ...]) -> str:
    """Stable hash for chrome_e2e submission idempotency."""
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if run_id:
        payload = f"submission:{run_id}".encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]
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


def _infer_lane_from_record(record: _DedupeRecord) -> str:
    raw_lane = record.get("lane")
    if isinstance(raw_lane, str) and raw_lane in {"READ", "LIVE_AGENT"}:
        return raw_lane
    argv = record.get("argv") or []
    joined = " ".join(str(part) for part in argv).lower()
    if "extension_bridge" in joined:
        return "READ"
    if "live_agent" in joined or "file_write_empty" in joined:
        return "LIVE_AGENT"
    return ""


def _max_holder_wall_sec(record: _DedupeRecord | None = None) -> float:
    """Lane-aware chrome_e2e wall — READ sessions must not inherit LIVE 1110s dedupe lock."""
    from dev_gate_contract import (
        LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC,
        READ_CHROME_E2E_PYTEST_TIMEOUT_SEC,
    )

    lane = ""
    if record is not None:
        lane = _infer_lane_from_record(record)
    if not lane:
        lane = os.environ.get("MYRM_E2E_LANE", "")
    if lane == "READ":
        return float(READ_CHROME_E2E_PYTEST_TIMEOUT_SEC)
    if lane == "LIVE_AGENT":
        return float(LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC)
    return float(LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC)


def _record_is_stale(record: _DedupeRecord, *, now: float) -> bool:
    holder_pid = record.get("holderPid")
    if not isinstance(holder_pid, int):
        return True
    if not _pid_alive(holder_pid):
        return True
    acquired_at = record.get("acquiredAt")
    if isinstance(acquired_at, (int, float)) and now - float(
        acquired_at
    ) > _max_holder_wall_sec(record):
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
    duplicate = find_duplicate_pid(
        fingerprint, exclude_pids=(resolved_pid, os.getppid())
    )
    if duplicate is not None:
        print(
            f"E2E_DEDUPE_HOLDER_RUNNING: holder_pid={duplicate} fingerprint={fingerprint} — "
            "existing chrome_e2e run in progress; read ./myrm e2e-context "
            "E2E_TEST_PROGRESS (do not relaunch; do not stop other pytest)",
            file=sys.stderr,
        )
        print(
            f"E2E_PYTEST_DEDUPE_DENIED: duplicate chrome_e2e session "
            f"fingerprint={fingerprint} holder_pid={duplicate} — "
            "wait for the existing run or stop relaunching the same test",
            file=sys.stderr,
        )
        raise SystemExit(2)
    batch_key = file_batch_key(argv)
    scope_key = e2e_file_scope_key(argv)
    execution_mode = os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper()
    if execution_mode == "SHARED" and not _is_guardrail_file_scope(scope_key):
        # P1: SHARED logical sessions must not whole-file dedupe block peers.
        # Exception: guardrail bash signoff is a maintenance singleton (Epic A §20 / R297).
        scope_key = None
        batch_key = None
    batch_flock_handle = None
    lock_key = scope_key or batch_key
    if lock_key is not None:
        batch_root = _file_batch_root()
        batch_root.mkdir(parents=True, exist_ok=True)
        batch_flock_handle = open(batch_root / ".claim.lock", "a+", encoding="utf-8")
        fcntl.flock(batch_flock_handle.fileno(), fcntl.LOCK_EX)
        scope_duplicate = find_file_scope_duplicate(
            lock_key, exclude_pids=(resolved_pid, os.getppid())
        )
        if scope_duplicate is not None:
            fcntl.flock(batch_flock_handle.fileno(), fcntl.LOCK_UN)
            batch_flock_handle.close()
            print(
                f"E2E_FILE_SCOPE_DEDUPE_DENIED: scope_key={lock_key} "
                f"holder_pid={scope_duplicate} — "
                "another chrome_e2e run targets the same e2e file; "
                "wait for it to finish (do not launch whole-file and ::node in parallel)",
                file=sys.stderr,
            )
            raise SystemExit(2)
    try:
        now = time.time()
        lane = os.environ.get("MYRM_E2E_LANE", "")
        record: _DedupeRecord = {
            "fingerprint": fingerprint,
            "holderPid": resolved_pid,
            "parentPid": os.getppid(),
            "argv": list(_normalize_argv(argv)),
            "acquiredAt": now,
            "heartbeatAt": now,
        }
        if lane in {"READ", "LIVE_AGENT"}:
            record["lane"] = lane
        path = _record_path(fingerprint)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(path)
        if lock_key is not None:
            batch_record: _DedupeRecord = {
                "fingerprint": lock_key,
                "holderPid": resolved_pid,
                "parentPid": os.getppid(),
                "argv": list(_normalize_argv(argv)),
                "acquiredAt": now,
                "heartbeatAt": now,
            }
            batch_path = _file_batch_record_path(lock_key)
            batch_tmp = batch_path.with_suffix(".json.tmp")
            batch_tmp.write_text(
                json.dumps(batch_record, indent=2, sort_keys=True), encoding="utf-8"
            )
            batch_tmp.replace(batch_path)
    finally:
        if batch_flock_handle is not None:
            fcntl.flock(batch_flock_handle.fileno(), fcntl.LOCK_UN)
            batch_flock_handle.close()


def release_session_lock(fingerprint: str, *, holder_pid: int | None = None) -> None:
    resolved_pid = holder_pid if holder_pid is not None else os.getpid()
    path = _record_path(fingerprint)
    record = _load_record(path)
    if record is None:
        return
    if record.get("holderPid") != resolved_pid:
        return
    path.unlink(missing_ok=True)
    batch_root = _file_batch_root()
    if batch_root.is_dir():
        for batch_path in batch_root.glob("*.json"):
            batch_record = _load_record(batch_path)
            if batch_record is None:
                batch_path.unlink(missing_ok=True)
                continue
            if batch_record.get("holderPid") == resolved_pid:
                batch_path.unlink(missing_ok=True)
