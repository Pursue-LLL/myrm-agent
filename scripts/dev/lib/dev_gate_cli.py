"""Autostarting CLI client for the Chrome E2E Dev Gate coordinator."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import secrets
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

_START_TIMEOUT_SEC = 2.0


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


def _ping(socket_path: Path) -> bool:
    try:
        request(
            {"operation": "snapshot", "session_id": "__health__"},
            socket_path=socket_path,
            timeout_sec=0.5,
        )
        return True
    except (ConnectionError, OSError, RuntimeError, TimeoutError):
        return False


def ensure_coordinator(
    *,
    socket_path: Path | None = None,
    database_path: Path | None = None,
) -> Path | None:
    socket_target = normalized_socket_path(socket_path or default_socket_path())
    database_target = (database_path or default_store_path()).resolve()
    disabled_path = database_target.with_suffix(".socket-disabled")
    if disabled_path.is_file():
        disabled_age = time.time() - disabled_path.stat().st_mtime
        if disabled_age < 60.0:
            return None
        disabled_path.unlink(missing_ok=True)
    if _ping(socket_target):
        return socket_target
    with _startup_lock(database_target):
        if _ping(socket_target):
            return socket_target
        log_path = database_target.with_name("coordinator.log")
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("ab", buffering=0) as log_handle:
            subprocess.Popen(
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
        f"DEV_GATE_COORDINATOR_START_TIMEOUT: socket={socket_target} "
        f"log={log_path}"
    )


def send(payload: dict[str, object]) -> dict[str, object]:
    socket_path = ensure_coordinator()
    if socket_path is None:
        return CoordinatorService(DevGateStore(default_store_path())).handle(payload)
    return request(payload, socket_path=socket_path)


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


def _private_admit(args: argparse.Namespace) -> int:
    started = time.monotonic()
    next_progress = 0.0
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
        from cleanup_observed_seal import observe_cleanup_seal

        snapshot = send(
            {
                "operation": "snapshot",
                "session_id": args.session_id,
            }
        )
        session = snapshot.get("session")
        ownership = session.get("ownership") if isinstance(session, dict) else None
        owned_pages: list[str] = []
        owned_context = ""
        if isinstance(ownership, dict):
            pages_raw = ownership.get("page_ids", [])
            if isinstance(pages_raw, list):
                owned_pages = [page_id for page_id in pages_raw if isinstance(page_id, str)]
            owned_context = str(ownership.get("browser_context_id", ""))
        requested_at = time.time()
        released_lease = args.released_lease_id.strip()
        ledger_cleaned, sealed = observe_cleanup_seal(
            released_lease_id=released_lease,
            owned_page_ids=tuple(owned_pages),
            owned_context_id=owned_context,
        )
        payload["receipt"] = {
            "closed_page_ids": [],
            "closed_context_id": args.closed_context_id,
            "released_lease_id": released_lease,
            "released_runtime_id": args.released_runtime_id,
            "ledger_cleaned": ledger_cleaned,
            "sealed": sealed,
            "requested_at": requested_at,
            "observed_at": time.time() if sealed else 0.0,
            "completed_at": time.time(),
        }
    elif args.command == "finish":
        payload["succeeded"] = args.succeeded
        payload["failure_token"] = args.failure_token
    print(json.dumps(send(payload), separators=(",", ":"), sort_keys=True))
    return 0


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
    submit.add_argument("--execution-mode", choices=("SHARED", "PRIVATE"), required=True)
    submit.add_argument(
        "--access-scope",
        choices=("READ", "NAMESPACE_WRITE", "GLOBAL_WRITE"),
        required=True,
    )
    submit.add_argument("--workload", choices=("STANDARD", "LIVE", "DESKTOP"), required=True)
    submit.add_argument("--namespace", default="")
    submit.add_argument("--priority", type=int, default=0)
    submit.add_argument("--private-credits", type=int, default=1)
    submit.add_argument("--hard-timeout-sec", type=float, default=600.0)
    submit.set_defaults(handler=_submit)

    private_admit = commands.add_parser("private_admit")
    private_admit.add_argument("--session-id", required=True)
    private_admit.add_argument("--owner-token", required=True)
    private_admit.set_defaults(handler=_private_admit)

    for command in (
        "transition",
        "heartbeat",
        "cleanup",
        "private_release",
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
