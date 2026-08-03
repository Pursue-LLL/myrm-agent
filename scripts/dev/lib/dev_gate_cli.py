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


def _ping(socket_path: Path, *, timeout_sec: float = 0.5) -> bool:
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
        disabled_age = time.time() - disabled_path.stat().st_mtime
        if disabled_age < 60.0:
            return None
        disabled_path.unlink(missing_ok=True)
    _reconcile_coordinator_singleton(
        socket_target=socket_target,
        database_target=database_target,
        pid_path=pid_path,
    )
    _clear_stale_coordinator_pid(pid_path)
    live_pid = _read_coordinator_pid(pid_path)
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
            try:
                socket_target.unlink(missing_ok=True)
            except OSError:
                return None
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


def _handle_in_process(payload: dict[str, object]) -> dict[str, object]:
    last_exc: sqlite3.OperationalError | None = None
    for attempt in range(8):
        try:
            return CoordinatorService(DevGateStore(default_store_path())).handle(
                payload
            )
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
        "reap",
        "heartbeat",
        "finish",
        "cleanup",
    }:
        timeout_sec = 30.0
    if isinstance(operation, str) and operation == "cleanup":
        timeout_sec = 60.0
    if operation == "wait_event":
        budget_raw = payload.get("budget_sec")
        if isinstance(budget_raw, (int, float)):
            timeout_sec = max(5.0, float(budget_raw) + 5.0)
        else:
            timeout_sec = 35.0
    try:
        return request(payload, socket_path=socket_path, timeout_sec=timeout_sec)
    except FileNotFoundError:
        socket_path = ensure_coordinator()
        if socket_path is None:
            return _handle_in_process(payload)
        return request(payload, socket_path=socket_path, timeout_sec=timeout_sec)
    except RuntimeError as exc:
        message = str(exc)
        if "DEV_GATE_COORDINATOR_ERROR" in message and "Expecting value" in message:
            return _handle_in_process(payload)
        if "timeout" in message.lower() or "timed out" in message.lower():
            return _handle_in_process(payload)
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


def _private_admit(args: argparse.Namespace) -> int:
    started = time.monotonic()
    next_progress = 0.0
    after_event_id = 0
    while True:
        response = send(
            {
                "operation": "private_admit",
                "session_id": args.session_id,
                "owner_token": args.owner_token,
            }
        )
        admission = response.get("admission")
        if not isinstance(admission, dict):
            raise RuntimeError("private admission response missing")
        if admission.get("granted") is True:
            print(json.dumps(admission, separators=(",", ":"), sort_keys=True))
            return 0
        elapsed = time.monotonic() - started
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
            waited = send(
                {
                    "operation": "wait_event",
                    "session_id": args.session_id,
                    "event_types": ["PRIVATE_ADMIT_GRANTED"],
                    "after_event_id": after_event_id,
                    "budget_sec": wait_budget,
                }
            )
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
    elif args.command == "cleanup":
        from cleanup_observed_seal import (
            collect_cdp_target_ids,
            lease_bound_target_ids,
            lease_released,
            physical_targets_absent,
            poll_physical_targets_absent,
        )

        requested_at = time.time()
        released_lease = args.released_lease_id.strip()
        ledger_cleaned = lease_released(released_lease)
        if not ledger_cleaned:
            for _ in range(3):
                time.sleep(1.0)
                if lease_released(released_lease):
                    ledger_cleaned = True
                    break
        bound = lease_bound_target_ids(released_lease)
        if bound:
            physical_released = poll_physical_targets_absent(
                lease_id=released_lease,
                timeout_sec=15.0,
            )
        else:
            physical_released = physical_targets_absent(lease_id=released_lease)
        cdp_after = collect_cdp_target_ids()
        sealed = ledger_cleaned and physical_released is True
        payload["receipt"] = {
            "closed_page_ids": list(bound),
            "closed_context_id": args.closed_context_id,
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
    elif args.command == "finish":
        payload["succeeded"] = args.succeeded
        payload["failure_token"] = args.failure_token
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
    json_stream = sys.stderr if args.command in {"cleanup", "finish"} else sys.stdout
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
        "cleanup",
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
