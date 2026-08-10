"""Autostarting CLI client for the Chrome E2E Dev Gate coordinator."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
import signal
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from dev_gate_coordinator import (
    CoordinatorService,
    default_socket_path,
    normalized_socket_path,
    request,
)
from dev_gate_store import DevGateStore, default_store_path

_START_TIMEOUT_SEC = 8.0
_PING_WAIT_SEC = 10.0
_SUBMIT_REQUEST_TIMEOUT_SEC = 120.0

_IN_PROCESS_SERVICE: CoordinatorService | None = None
_IN_PROCESS_SERVICE_LOCK = threading.Lock()

_COORDINATOR_CODE_FP_FILES: tuple[str, ...] = (
    "dev_gate_coordinator.py",
    "dev_gate_cli.py",
    "dev_gate_contract.py",
    "private_resource_controller.py",
    "dev_gate_store.py",
    "e2e_stale_lease_reap.py",
    "e2e_pytest_dedupe.py",
    "e2e_session_registry.py",
    "stack_mutation_policy.py",
)


def coordinator_code_fingerprint() -> str:
    lib = Path(__file__).resolve().parent
    parts: list[str] = []
    for name in _COORDINATOR_CODE_FP_FILES:
        path = lib / name
        if path.is_file():
            parts.append(f"{name}:{path.stat().st_mtime_ns}")
    return "|".join(parts)


def _coordinator_code_stamp_path(database_target: Path) -> Path:
    return database_target.with_name("coordinator.code-fp")


def _write_coordinator_code_stamp(database_target: Path) -> None:
    stamp_path = _coordinator_code_stamp_path(database_target)
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    stamp_path.write_text(coordinator_code_fingerprint(), encoding="utf-8")


def _coordinator_code_stale(*, database_target: Path, live_pid: int | None) -> bool:
    if live_pid is None or not _pid_alive(live_pid):
        return False
    stamp_path = _coordinator_code_stamp_path(database_target)
    if not stamp_path.is_file():
        return True
    try:
        recorded = stamp_path.read_text(encoding="utf-8").strip()
    except OSError:
        return True
    return recorded != coordinator_code_fingerprint()


def _restart_coordinator_for_code_drift(
    *,
    live_pid: int,
    socket_target: Path,
    pid_path: Path,
) -> None:
    try:
        os.kill(live_pid, signal.SIGTERM)
    except OSError:
        pass
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _pid_alive(live_pid):
            break
        time.sleep(0.05)
    _clear_stale_coordinator_pid(pid_path)
    try:
        socket_target.unlink(missing_ok=True)
    except OSError:
        pass


def _coordinator_pid_path(database_path: Path) -> Path:
    return database_path.with_name("coordinator.pid")


def _read_coordinator_pid(pid_path: Path) -> int | None:
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw.isdigit():
        return None
    return int(raw)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _write_coordinator_pid(pid_path: Path, pid: int) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(f"{pid}\n", encoding="utf-8")
    os.chmod(pid_path, 0o600)


def _clear_stale_coordinator_pid(pid_path: Path) -> None:
    existing = _read_coordinator_pid(pid_path)
    if existing is None:
        return
    if _pid_alive(existing):
        return
    pid_path.unlink(missing_ok=True)


def _wait_for_ping(socket_path: Path, *, budget_sec: float) -> bool:
    deadline = time.monotonic() + max(0.1, budget_sec)
    while time.monotonic() < deadline:
        if _ping(socket_path):
            return True
        time.sleep(0.25)
    return False


@contextmanager
def _startup_lock(database_path: Path) -> Iterator[None]:
    lock_path = database_path.with_suffix(".startup.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        os.chmod(lock_path, 0o600)
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _ping(socket_path: Path, *, timeout_sec: float = 3.0) -> bool:
    try:
        request(
            {"operation": "snapshot", "session_id": "__health__"},
            socket_path=socket_path,
            timeout_sec=timeout_sec,
        )
        return True
    except (ConnectionError, OSError, RuntimeError, TimeoutError):
        return False


def _list_coordinator_serve_pids(
    *,
    socket_target: Path,
    database_target: Path,
) -> list[int]:
    """PIDs for coordinator serve processes bound to this socket/database."""
    try:
        result = subprocess.run(
            ["pgrep", "-lf", "dev_gate_coordinator.py serve"],
            capture_output=True,
            text=True,
            timeout=3.0,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []
    socket_str = str(socket_target)
    database_str = str(database_target)
    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) < 2:
            continue
        pid_str, command = parts[0], parts[1]
        if socket_str not in command and database_str not in command:
            continue
        try:
            pids.append(int(pid_str))
        except ValueError:
            continue
    return pids


def _reconcile_coordinator_singleton(
    *,
    socket_target: Path,
    database_target: Path,
    pid_path: Path,
) -> None:
    """Keep one healthy coordinator; terminate orphan serve processes (infra only)."""
    serve_pids = _list_coordinator_serve_pids(
        socket_target=socket_target,
        database_target=database_target,
    )
    alive_pids = [pid for pid in serve_pids if _pid_alive(pid)]
    if not alive_pids:
        _clear_stale_coordinator_pid(pid_path)
        return

    if _ping(socket_target) or _wait_for_ping(socket_target, budget_sec=2.0):
        canonical = _read_coordinator_pid(pid_path)
        keeper: int | None = None
        if canonical is not None and canonical in alive_pids:
            keeper = canonical
        else:
            keeper = alive_pids[0]
        _write_coordinator_pid(pid_path, keeper)
        for pid in alive_pids:
            if pid == keeper:
                continue
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                continue
        return

    for pid in alive_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    _clear_stale_coordinator_pid(pid_path)
    try:
        socket_target.unlink(missing_ok=True)
    except OSError:
        pass


def _eliminate_coordinator_herd(
    *,
    socket_target: Path,
    database_target: Path,
    pid_path: Path,
) -> None:
    """Drop orphan coordinator serve processes before spawning a replacement."""
    _reconcile_coordinator_singleton(
        socket_target=socket_target,
        database_target=database_target,
        pid_path=pid_path,
    )
    serve_pids = _list_coordinator_serve_pids(
        socket_target=socket_target,
        database_target=database_target,
    )
    if len(serve_pids) <= 1 and (
        _ping(socket_target) or _wait_for_ping(socket_target, budget_sec=2.0)
    ):
        return
    for pid in serve_pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    time.sleep(0.5)
    for pid in _list_coordinator_serve_pids(
        socket_target=socket_target,
        database_target=database_target,
    ):
        if not _pid_alive(pid):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            continue
    _clear_stale_coordinator_pid(pid_path)
    try:
        socket_target.unlink(missing_ok=True)
    except OSError:
        pass


def _coordinator_herd_active(
    *,
    socket_target: Path,
    database_target: Path,
) -> bool:
    return bool(
        _list_coordinator_serve_pids(
            socket_target=socket_target,
            database_target=database_target,
        )
    )


def ensure_coordinator(
    *,
    socket_path: Path | None = None,
    database_path: Path | None = None,
) -> Path | None:
    socket_target = normalized_socket_path(socket_path or default_socket_path())
    database_target = (database_path or default_store_path()).resolve()
    disabled_path = database_target.with_suffix(".socket-disabled")
    pid_path = _coordinator_pid_path(database_target)
    if disabled_path.is_file():
        # Stale .socket-disabled must not block a live coordinator (R274).
        if _ping(socket_target):
            disabled_path.unlink(missing_ok=True)
        else:
            try:
                disabled_age = time.time() - disabled_path.stat().st_mtime
            except FileNotFoundError:
                disabled_age = 60.0
            if disabled_age < 60.0:
                # Parallel burst callers must wait for restart, not fail instantly (Phase C 4-lane).
                restart_budget = min(max(60.0 - disabled_age, 0.5), 45.0)
                if _wait_for_ping(socket_target, budget_sec=restart_budget):
                    disabled_path.unlink(missing_ok=True)
                    return socket_target
                disabled_path.unlink(missing_ok=True)
            else:
                disabled_path.unlink(missing_ok=True)
    _reconcile_coordinator_singleton(
        socket_target=socket_target,
        database_target=database_target,
        pid_path=pid_path,
    )
    _clear_stale_coordinator_pid(pid_path)
    live_pid = _read_coordinator_pid(pid_path)
    if live_pid is not None and _coordinator_code_stale(
        database_target=database_target, live_pid=live_pid
    ):
        _restart_coordinator_for_code_drift(
            live_pid=live_pid,
            socket_target=socket_target,
            pid_path=pid_path,
        )
        live_pid = None
    if live_pid is not None and _pid_alive(live_pid):
        if _ping(socket_target) or _wait_for_ping(
            socket_target, budget_sec=_PING_WAIT_SEC
        ):
            return socket_target
    if _ping(socket_target):
        return socket_target
    if socket_target.exists() and _wait_for_ping(
        socket_target, budget_sec=_PING_WAIT_SEC
    ):
        return socket_target
    with _startup_lock(database_target):
        _clear_stale_coordinator_pid(pid_path)
        live_pid = _read_coordinator_pid(pid_path)
        if live_pid is not None and _pid_alive(live_pid):
            if _ping(socket_target) or _wait_for_ping(
                socket_target, budget_sec=_PING_WAIT_SEC
            ):
                return socket_target
        if _ping(socket_target):
            return socket_target
        if socket_target.exists():
            if _wait_for_ping(socket_target, budget_sec=2.0):
                return socket_target
            live_pid = _read_coordinator_pid(pid_path)
            if live_pid is not None and _pid_alive(live_pid):
                if _wait_for_ping(socket_target, budget_sec=_PING_WAIT_SEC):
                    return socket_target
            # R273: stale socket blocks all waiters — remove and spawn one coordinator.
            _eliminate_coordinator_herd(
                socket_target=socket_target,
                database_target=database_target,
                pid_path=pid_path,
            )
        log_path = database_target.with_name("coordinator.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab", buffering=0) as log_handle:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    str(Path(__file__).with_name("dev_gate_coordinator.py")),
                    "serve",
                    "--socket",
                    str(socket_target),
                    "--database",
                    str(database_target),
                ],
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                start_new_session=True,
                close_fds=True,
            )
        _write_coordinator_pid(pid_path, proc.pid)
        _write_coordinator_code_stamp(database_target)
        deadline = time.monotonic() + _START_TIMEOUT_SEC
        while time.monotonic() < deadline:
            if _ping(socket_target):
                return socket_target
            time.sleep(0.05)
    log_path = database_target.with_name("coordinator.log")
    try:
        log_text = log_path.read_text(encoding="utf-8")
    except OSError:
        log_text = ""
    if "PermissionError" in log_text or "Operation not permitted" in log_text:
        disabled_path.touch(mode=0o600, exist_ok=True)
        return None
    raise RuntimeError(
        f"DEV_GATE_COORDINATOR_START_TIMEOUT: socket={socket_target} " f"log={log_path}"
    )


def _in_process_service() -> CoordinatorService:
    global _IN_PROCESS_SERVICE
    with _IN_PROCESS_SERVICE_LOCK:
        if _IN_PROCESS_SERVICE is None:
            _IN_PROCESS_SERVICE = CoordinatorService(DevGateStore(default_store_path()))
        return _IN_PROCESS_SERVICE


def _socket_live(socket_path: Path | None) -> bool:
    return socket_path is not None and _ping(socket_path)


def _request_via_socket_with_retries(
    payload: dict[str, object],
    *,
    socket_path: Path,
    timeout_sec: float,
    attempts: int = 5,
) -> dict[str, object]:
    """Retry socket RPC while coordinator is live — never compete via in-process SQLite."""
    target = socket_path
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            return request(payload, socket_path=target, timeout_sec=timeout_sec)
        except (RuntimeError, TimeoutError, ConnectionError, OSError) as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                break
            time.sleep(min(0.12 * float(attempt + 1), 1.5))
            refreshed = ensure_coordinator()
            if refreshed is None or not _socket_live(refreshed):
                break
            target = refreshed
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("DEV_GATE_SOCKET_RETRY_EXHAUSTED")


def _handle_in_process(payload: dict[str, object]) -> dict[str, object]:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(8):
        try:
            return _in_process_service().handle(payload)
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt >= 7:
                raise
            last_exc = exc
            time.sleep(min(0.1 * (2**attempt), 2.0))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("DEV_GATE_IN_PROCESS_FAILED")


def send(payload: dict[str, object]) -> dict[str, object]:
    socket_path = ensure_coordinator()
    if socket_path is None:
        return _handle_in_process(payload)
    operation = payload.get("operation")
    timeout_sec = 10.0
    if isinstance(operation, str) and operation == "submit":
        timeout_sec = _SUBMIT_REQUEST_TIMEOUT_SEC
    if isinstance(operation, str) and operation in {
        "private_admit",
        "desktop_admit",
    }:
        timeout_sec = 90.0
    if isinstance(operation, str) and operation in {
        "reap",
        "heartbeat",
        "finish",
        "cleanup",
        "teardown_finish",
        "ownership",
        "snapshot",
        "transition",
    }:
        timeout_sec = 60.0 if operation == "reap" else 30.0
    if isinstance(operation, str) and operation in {"cleanup", "teardown_finish"}:
        from dev_gate_contract import dev_gate_teardown_finish_client_timeout_sec

        timeout_sec = float(dev_gate_teardown_finish_client_timeout_sec())
    if operation == "wait_event":
        budget_raw = payload.get("budget_sec")
        if isinstance(budget_raw, (int, float)):
            timeout_sec = max(5.0, float(budget_raw) + 5.0)
        else:
            timeout_sec = 35.0
    try:
        return _request_via_socket_with_retries(
            payload, socket_path=socket_path, timeout_sec=timeout_sec
        )
    except FileNotFoundError:
        last_missing: FileNotFoundError | None = None
        for attempt in range(8):
            socket_path = ensure_coordinator()
            if socket_path is None:
                return _handle_in_process(payload)
            try:
                return _request_via_socket_with_retries(
                    payload, socket_path=socket_path, timeout_sec=timeout_sec
                )
            except FileNotFoundError as exc:
                last_missing = exc
                time.sleep(min(0.15 * float(attempt + 1), 2.0))
        if last_missing is not None:
            if ensure_coordinator() is None:
                return _handle_in_process(payload)
            raise last_missing
        raise RuntimeError("DEV_GATE_SOCKET_RETRY_EXHAUSTED")
    except RuntimeError as exc:
        message = str(exc)
        decode_or_empty = "DEV_GATE_COORDINATOR_ERROR" in message and (
            "Expecting value" in message or "empty coordinator response" in message
        )
        if (
            decode_or_empty
            or "timeout" in message.lower()
            or "timed out" in message.lower()
        ):
            database_target = default_store_path().resolve()
            socket_target = normalized_socket_path(default_socket_path())
            pid_path = _coordinator_pid_path(database_target)
            for attempt in range(5):
                _reconcile_coordinator_singleton(
                    socket_target=socket_target,
                    database_target=database_target,
                    pid_path=pid_path,
                )
                socket_path = ensure_coordinator()
                if socket_path is None:
                    if _coordinator_herd_active(
                        socket_target=socket_target,
                        database_target=database_target,
                    ):
                        time.sleep(min(0.25 * float(attempt + 1), 1.0))
                        continue
                    return _handle_in_process(payload)
                if not _socket_live(socket_path):
                    if _coordinator_herd_active(
                        socket_target=socket_target,
                        database_target=database_target,
                    ):
                        time.sleep(min(0.25 * float(attempt + 1), 1.0))
                        continue
                    return _handle_in_process(payload)
                try:
                    extended = timeout_sec * (1.0 + 0.25 * float(attempt))
                    return _request_via_socket_with_retries(
                        payload,
                        socket_path=socket_path,
                        timeout_sec=extended,
                        attempts=3,
                    )
                except (RuntimeError, TimeoutError, ConnectionError, OSError):
                    if attempt + 1 >= 5:
                        raise
                    time.sleep(min(0.15 * float(attempt + 1), 1.0))
            raise
        raise


def _submit(args: argparse.Namespace) -> int:
    owner_token = args.owner_token or f"owner-{secrets.token_hex(16)}"
    namespace = args.namespace
    if args.access_scope == "NAMESPACE_WRITE" and not namespace:
        namespace = args.session_id
    response = send(
        {
            "operation": "submit",
            "session_id": args.session_id,
            "owner_pid": args.owner_pid,
            "owner_token": owner_token,
            "owner_process_start": args.owner_process_start,
            "owner_boot_id": args.owner_boot_id,
            "test_node_id": args.test_node_id,
            "hard_deadline": time.time() + args.hard_timeout_sec,
            "policy": {
                "execution_mode": args.execution_mode,
                "access_scope": args.access_scope,
                "workload": args.workload,
                "namespace": namespace,
                "priority": args.priority,
                "private_credits": args.private_credits,
            },
        }
    )
    print(
        json.dumps(
            {"owner_token": owner_token, **response},
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _private_admit_event_wait_enabled() -> bool:
    return os.environ.get("MYRM_DEV_GATE_EVENT_WAIT", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def _private_admit_wall_sec() -> float:
    from private_resource_controller import PRIVATE_ADMIT_TIMEOUT_SEC

    override = os.environ.get("MYRM_PRIVATE_ADMIT_WALL_SEC", "").strip()
    if override:
        return max(1.0, float(override))
    return PRIVATE_ADMIT_TIMEOUT_SEC


def _private_admit_terminal_error(exc: BaseException) -> bool:
    message = str(exc)
    terminal_markers = (
        "session is not admissible",
        "PRIVATE_ADMIT_TIMEOUT",
        "session owner mismatch",
        "session not found",
        "shared session cannot enter private admission",
    )
    return any(marker in message for marker in terminal_markers)


def _private_admit(args: argparse.Namespace) -> int:
    started = time.monotonic()
    wall_sec = _private_admit_wall_sec()
    next_progress = 0.0
    after_event_id = 0
    while True:
        elapsed = time.monotonic() - started
        if elapsed >= wall_sec:
            raise TimeoutError(
                f"PRIVATE_ADMIT_WALL_TIMEOUT: session={args.session_id} "
                f"waited={int(elapsed)}s wall={int(wall_sec)}s"
            )
        try:
            response = send(
                {
                    "operation": "private_admit",
                    "session_id": args.session_id,
                    "owner_token": args.owner_token,
                }
            )
        except (RuntimeError, TimeoutError, OSError, ConnectionError) as exc:
            if _private_admit_terminal_error(exc):
                raise
            raise RuntimeError(
                f"PRIVATE_ADMIT_COORDINATOR_ERROR: session={args.session_id} "
                f"elapsed={int(elapsed)}s detail={exc}"
            ) from exc
        admission = response.get("admission")
        if not isinstance(admission, dict):
            raise RuntimeError("private admission response missing")
        if admission.get("granted") is True:
            print(json.dumps(admission, separators=(",", ":"), sort_keys=True))
            return 0
        if elapsed >= next_progress:
            print(
                "E2E_PRIVATE_ADMIT_WAIT: "
                f"position={admission.get('queue_position')} "
                f"active={admission.get('active_credits')}/"
                f"{admission.get('capacity_credits')} elapsed={int(elapsed)}s",
                file=sys.stderr,
                flush=True,
            )
            next_progress = elapsed + 30.0
        if _private_admit_event_wait_enabled():
            wait_budget = float(admission.get("next_progress_sec", 30.0))
            wait_budget = max(1.0, min(wait_budget, 30.0))
            try:
                waited = send(
                    {
                        "operation": "wait_event",
                        "session_id": args.session_id,
                        "event_types": ["PRIVATE_ADMIT_GRANTED"],
                        "after_event_id": after_event_id,
                        "budget_sec": wait_budget,
                    }
                )
            except (RuntimeError, TimeoutError, OSError, ConnectionError) as exc:
                if _private_admit_terminal_error(exc):
                    raise
                print(
                    "E2E_PRIVATE_ADMIT_WAIT_EVENT_RETRY: "
                    f"session={args.session_id} elapsed={int(elapsed)}s detail={exc}",
                    file=sys.stderr,
                    flush=True,
                )
                time.sleep(min(1.0, wait_budget))
                continue
            event = waited.get("event")
            if isinstance(event, dict):
                event_id = event.get("event_id")
                if isinstance(event_id, int):
                    after_event_id = event_id
                continue
        time.sleep(min(1.0, float(admission.get("next_progress_sec", 1.0))))


def _desktop_admit(args: argparse.Namespace) -> int:
    started = time.monotonic()
    next_progress = 0.0
    while True:
        response = send(
            {
                "operation": "desktop_admit",
                "session_id": args.session_id,
                "owner_token": args.owner_token,
            }
        )
        admission = response.get("admission")
        if not isinstance(admission, dict):
            raise RuntimeError("desktop seat admission response missing")
        if admission.get("granted") is True:
            print(json.dumps(admission, separators=(",", ":"), sort_keys=True))
            return 0
        elapsed = time.monotonic() - started
        if elapsed >= next_progress:
            print(
                "E2E_DESKTOP_SEAT_WAIT: "
                f"position={admission.get('queue_position')} "
                f"active={admission.get('active_seats')}/"
                f"{admission.get('capacity_seats')} elapsed={int(elapsed)}s",
                file=sys.stderr,
                flush=True,
            )
            next_progress = elapsed + 30.0
        time.sleep(min(1.0, float(admission.get("next_progress_sec", 1.0))))


def _load_session_ownership(session_id: str) -> tuple[tuple[str, ...], str]:
    from dev_gate_store import DevGateStore, default_store_path

    record = DevGateStore(default_store_path()).get(session_id.strip())
    if record is None:
        return (), ""
    return record.ownership.page_ids, record.ownership.browser_context_id


def _request_dev_gate_destroy(session_id: str, owner_token: str) -> None:
    """Best-effort coordinator-owned destroy (clear keyed ownership).

    Failure keeps the pending ownership visible so the seal observation stays
    fail-closed instead of reporting a synthetic green.
    """
    try:
        send(
            {
                "operation": "destroy",
                "session_id": session_id,
                "owner_token": owner_token,
            }
        )
    except (RuntimeError, OSError) as exc:
        print(f"DEV_GATE_DESTROY_WARN: {exc}", file=sys.stderr)


def _build_observed_cleanup_receipt(args: argparse.Namespace) -> dict[str, object]:
    from cleanup_observed_seal import (
        collect_cdp_target_ids,
        lease_released,
        observe_cleanup_seal,
        poll_physical_targets_absent,
        physical_targets_absent,
    )

    requested_at = time.time()
    released_lease = args.released_lease_id.strip()
    owned_pages, owned_context = _load_session_ownership(args.session_id)
    if args.closed_context_id.strip():
        owned_context = args.closed_context_id.strip()
    closed_pages = owned_pages
    closed_context = owned_context

    # P0-A destroy step: coordinator-owned destroy clears keyed ownership so the
    # ownership_cleared seal check is observably true. Physical page/context
    # destroy already happened inside the pytest process.
    if owned_pages or owned_context.strip():
        _request_dev_gate_destroy(args.session_id, args.owner_token)
        owned_pages, owned_context = _load_session_ownership(args.session_id)
        if args.closed_context_id.strip():
            owned_context = args.closed_context_id.strip()

    ledger_cleaned = lease_released(released_lease)
    if not ledger_cleaned:
        for _ in range(3):
            time.sleep(1.0)
            if lease_released(released_lease):
                ledger_cleaned = True
                break

    if released_lease:
        physical_released = poll_physical_targets_absent(
            lease_id=released_lease,
            timeout_sec=15.0,
        )
    else:
        physical_released = physical_targets_absent(lease_id=released_lease)

    ledger_cleaned, sealed = observe_cleanup_seal(
        released_lease_id=released_lease,
        owned_page_ids=owned_pages,
        owned_context_id=owned_context,
    )
    cdp_after = collect_cdp_target_ids()
    return {
        "closed_page_ids": list(closed_pages),
        "closed_context_id": closed_context,
        "released_lease_id": released_lease,
        "released_runtime_id": args.released_runtime_id,
        "ledger_cleaned": ledger_cleaned,
        "physical_released": physical_released,
        "cdp_target_ids_after": sorted(cdp_after) if cdp_after is not None else [],
        "sealed": sealed,
        "requested_at": requested_at,
        "observed_at": time.time() if sealed else 0.0,
        "completed_at": time.time(),
    }


def _simple_operation(args: argparse.Namespace) -> int:
    payload: dict[str, object] = {
        "operation": args.command,
        "session_id": args.session_id,
        "owner_token": args.owner_token,
    }
    if args.command == "transition":
        payload["target"] = args.target
        payload["current_node"] = args.current_node
        payload["failure_token"] = args.failure_token
    elif args.command == "heartbeat":
        payload["current_node"] = args.current_node
    elif args.command in {"cleanup", "teardown-finish"}:
        payload["receipt"] = _build_observed_cleanup_receipt(args)
        if args.command == "teardown-finish":
            payload["operation"] = "teardown_finish"
            payload["succeeded"] = args.succeeded
            payload["failure_token"] = args.failure_token
    elif args.command == "finish":
        payload["succeeded"] = args.succeeded
        payload["failure_token"] = args.failure_token
    if args.command in {"finish", "teardown-finish"} and args.pytest_evidence_hash:
        payload["pytest_evidence_hash"] = args.pytest_evidence_hash
    try:
        response = send(payload)
    except RuntimeError as exc:
        message = str(exc)
        if "TerminalConflictError" in message or "cannot finish succeeded" in message:
            print(message, file=sys.stderr)
            return 1
        if "CleanupUnsealedError" in message or "cleanup not sealed" in message:
            print(message, file=sys.stderr)
            return 1
        raise
    # cleanup/finish run inside test.sh EXIT trap; stdout would pollute detach pytest logs.
    json_stream = (
        sys.stderr
        if args.command
        in {
            "cleanup",
            "finish",
            "teardown-finish",
        }
        else sys.stdout
    )
    print(json.dumps(response, separators=(",", ":"), sort_keys=True), file=json_stream)
    if args.command == "cleanup":
        if os.environ.get("MYRM_E2E_RELAX_DEV_GATE_TERMINAL", "").strip() == "1":
            return 0
        session = response.get("session")
        cleanup = session.get("cleanup") if isinstance(session, dict) else None
        if isinstance(cleanup, dict) and cleanup.get("sealed") is True:
            return 0
        print("E2E_DEV_GATE_CLEANUP_UNSEALED: observed seal missing", file=sys.stderr)
        return 1
    if args.command == "teardown-finish":
        if os.environ.get("MYRM_E2E_RELAX_DEV_GATE_TERMINAL", "").strip() == "1":
            return 0
        session = response.get("session")
        if not isinstance(session, dict):
            print("E2E_DEV_GATE_TEARDOWN_FINISH_MISSING_SESSION", file=sys.stderr)
            return 1
        cleanup = session.get("cleanup")
        if args.succeeded:
            if not isinstance(cleanup, dict) or cleanup.get("sealed") is not True:
                print("E2E_DEV_GATE_TEARDOWN_FINISH_UNSEALED", file=sys.stderr)
                return 1
            if (
                session.get("state") != "SUCCEEDED"
                or session.get("outcome") != "PASSED"
            ):
                print(
                    "E2E_DEV_GATE_TEARDOWN_FINISH_TERMINAL_MISMATCH: "
                    f"state={session.get('state')} outcome={session.get('outcome')}",
                    file=sys.stderr,
                )
                return 1
        return 0
    if args.command == "finish" and args.succeeded:
        session = response.get("session")
        if not isinstance(session, dict):
            print("E2E_DEV_GATE_FINISH_MISSING_SESSION", file=sys.stderr)
            return 1
        if session.get("state") != "SUCCEEDED" or session.get("outcome") != "PASSED":
            print(
                "E2E_DEV_GATE_FINISH_TERMINAL_MISMATCH: "
                f"state={session.get('state')} outcome={session.get('outcome')}",
                file=sys.stderr,
            )
            return 1
    return 0


def _coordinator_reap(_args: argparse.Namespace) -> int:
    """P0-A: sole entry for hung/stale pytest SIGINT and store deadline reap."""
    os.environ["MYRM_DEV_GATE_COORDINATOR_REAP"] = "1"
    from e2e_stale_lease_reap import (  # noqa: PLC0415
        maybe_reap_excess_wave_leases,
        maybe_reap_hung_chrome_e2e_pytest,
        maybe_reap_stale_empty_mux_contexts,
        maybe_reap_stale_heartbeat_leases,
    )

    store_reaped = send({"operation": "reap"})
    reaped_ids = store_reaped.get("reaped_session_ids", [])
    stale = maybe_reap_stale_heartbeat_leases()
    mux_reaped = maybe_reap_stale_empty_mux_contexts()
    hung = maybe_reap_hung_chrome_e2e_pytest()
    excess = maybe_reap_excess_wave_leases()
    print(
        json.dumps(
            {
                "reaped_session_ids": (
                    reaped_ids if isinstance(reaped_ids, list) else list(reaped_ids)
                ),
                "stale_heartbeat_reaped": stale,
                "mux_idle_reaped": mux_reaped,
                "hung_reaped": hung,
                "excess_wave_reaped": excess,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


def _export_signoff_artifact(args: argparse.Namespace) -> int:
    payload: dict[str, object] = {
        "operation": "export_signoff_artifact",
        "output_path": args.output_path,
        "session_limit": args.session_limit,
        "event_limit": args.event_limit,
    }
    if args.session_id:
        payload["session_ids"] = list(args.session_id)
    response = send(payload)
    print(json.dumps(response, separators=(",", ":"), sort_keys=True))
    return 0


def _verify_signoff_artifact(args: argparse.Namespace) -> int:
    response = send(
        {
            "operation": "verify_signoff_artifact",
            "output_path": args.output_path,
        }
    )
    print(json.dumps(response, separators=(",", ":"), sort_keys=True))
    return 0 if response.get("valid") is True else 1


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    submit = commands.add_parser("submit")
    submit.add_argument("--session-id", required=True)
    submit.add_argument("--owner-pid", required=True, type=int)
    submit.add_argument("--owner-token", default="")
    submit.add_argument("--owner-process-start", default="")
    submit.add_argument("--owner-boot-id", default="")
    submit.add_argument("--test-node-id", required=True)
    submit.add_argument(
        "--execution-mode", choices=("SHARED", "PRIVATE"), required=True
    )
    submit.add_argument(
        "--access-scope",
        choices=("READ", "NAMESPACE_WRITE", "GLOBAL_WRITE"),
        required=True,
    )
    submit.add_argument(
        "--workload", choices=("STANDARD", "LIVE", "DESKTOP"), required=True
    )
    submit.add_argument("--namespace", default="")
    submit.add_argument("--priority", type=int, default=0)
    submit.add_argument("--private-credits", type=int, default=1)
    submit.add_argument("--hard-timeout-sec", type=float, default=600.0)
    submit.set_defaults(handler=_submit)

    private_admit = commands.add_parser("private_admit")
    private_admit.add_argument("--session-id", required=True)
    private_admit.add_argument("--owner-token", required=True)
    private_admit.set_defaults(handler=_private_admit)

    desktop_admit = commands.add_parser("desktop_admit")
    desktop_admit.add_argument("--session-id", required=True)
    desktop_admit.add_argument("--owner-token", required=True)
    desktop_admit.set_defaults(handler=_desktop_admit)

    reap = commands.add_parser("reap")
    reap.set_defaults(handler=_coordinator_reap)

    export_signoff = commands.add_parser("export_signoff_artifact")
    export_signoff.add_argument("--output-path", required=True)
    export_signoff.add_argument("--session-limit", type=int, default=200)
    export_signoff.add_argument("--event-limit", type=int, default=2000)
    export_signoff.add_argument(
        "--session-id",
        action="append",
        default=[],
        help="Run-scoped session id(s) to export; repeatable",
    )
    export_signoff.set_defaults(handler=_export_signoff_artifact)

    verify_signoff = commands.add_parser("verify_signoff_artifact")
    verify_signoff.add_argument("--output-path", required=True)
    verify_signoff.set_defaults(handler=_verify_signoff_artifact)

    for command in (
        "transition",
        "heartbeat",
        "destroy",
        "cleanup",
        "teardown-finish",
        "private_release",
        "desktop_release",
        "finish",
    ):
        operation = commands.add_parser(command)
        operation.add_argument("--session-id", required=True)
        operation.add_argument("--owner-token", required=True)
        operation.add_argument("--target", default="")
        operation.add_argument("--current-node", default="")
        operation.add_argument("--failure-token", default="")
        operation.add_argument("--succeeded", action="store_true")
        operation.add_argument("--pytest-evidence-hash", default="")
        operation.add_argument("--closed-context-id", default="")
        operation.add_argument("--released-lease-id", default="")
        operation.add_argument("--released-runtime-id", default="")
        operation.set_defaults(handler=_simple_operation)
    return parser


def main() -> int:
    args = _parser().parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
