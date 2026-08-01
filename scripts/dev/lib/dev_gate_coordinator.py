"""Unix-socket coordinator for the recoverable Chrome E2E session registry."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import cast

from dev_gate_session import (
    AccessScope,
    CleanupReceipt,
    ExecutionMode,
    SessionOwnership,
    SessionPolicy,
    SessionState,
    Workload,
)
from dev_gate_store import DevGateStore, default_store_path
from private_resource_controller import (
    PrivateResourceController,
    private_capacity_credits,
)
from desktop_seat_controller import (
    DesktopSeatController,
    desktop_seat_capacity,
)

_MAX_REQUEST_BYTES = 1_048_576


def default_socket_path() -> Path:
    override = os.environ.get("MYRM_DEV_GATE_SOCKET", "").strip()
    if override:
        return Path(override).resolve()
    return default_store_path().with_name("coordinator.sock")


def normalized_socket_path(path: Path) -> Path:
    resolved = path.resolve()
    if len(os.fsencode(resolved)) <= 96:
        return resolved
    digest = hashlib.sha256(os.fsencode(resolved)).hexdigest()[:16]
    short_root = Path(tempfile.gettempdir()) / f"myrm-dev-gate-{os.getuid()}"
    return short_root / f"{digest}.sock"


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"required text field missing: {key}")
    return value.strip()


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if not isinstance(value, int):
        raise ValueError(f"required integer field missing: {key}")
    return value


def _optional_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"field must be text: {key}")
    return value.strip()


class CoordinatorService:
    def __init__(
        self,
        store: DevGateStore,
        *,
        private_capacity: int | None = None,
        desktop_capacity: int | None = None,
    ) -> None:
        self.store = store
        self.private_controller = PrivateResourceController(
            store,
            capacity_credits=private_capacity or private_capacity_credits(),
        )
        self.desktop_controller = DesktopSeatController(
            store,
            capacity_seats=(
                desktop_capacity
                if desktop_capacity is not None
                else desktop_seat_capacity()
            ),
        )

    def handle(self, request: dict[str, object]) -> dict[str, object]:
        operation = _required_text(request, "operation")
        if operation == "reap":
            reaped = list(self.store.reap_abandoned())
            reaped.extend(self.store.reap_expired_deadlines())
            return {"reaped_session_ids": reaped}
        if operation == "submit":
            return self._submit(request)
        if operation == "transition":
            return self._transition(request)
        if operation == "heartbeat":
            record = self.store.heartbeat(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
                current_node=_optional_text(request, "current_node"),
            )
            return {"session": record.to_dict()}
        if operation == "ownership":
            return self._ownership(request)
        if operation == "cleanup":
            return self._cleanup(request)
        if operation == "finish":
            record = self.store.finish(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
                succeeded=request.get("succeeded") is True,
                failure_token=_optional_text(request, "failure_token"),
            )
            return {"session": record.to_dict()}
        if operation == "private_admit":
            admission = self.private_controller.admit(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
            )
            return {
                "admission": {
                    "granted": admission.granted,
                    "queue_position": admission.queue_position,
                    "active_credits": admission.active_credits,
                    "capacity_credits": admission.capacity_credits,
                    "waited_sec": admission.waited_sec,
                    "next_progress_sec": admission.next_progress_sec,
                }
            }
        if operation == "desktop_admit":
            admission = self.desktop_controller.admit(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
            )
            return {
                "admission": {
                    "granted": admission.granted,
                    "queue_position": admission.queue_position,
                    "active_seats": admission.active_seats,
                    "capacity_seats": admission.capacity_seats,
                    "waited_sec": admission.waited_sec,
                    "next_progress_sec": admission.next_progress_sec,
                }
            }
        if operation == "desktop_release":
            granted = self.desktop_controller.release(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
            )
            return {"granted_session_ids": list(granted)}
        if operation == "private_release":
            granted = self.private_controller.release(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
            )
            return {"granted_session_ids": list(granted)}
        if operation == "snapshot":
            session_id = _optional_text(request, "session_id")
            if session_id:
                record = self.store.get(session_id)
                return {
                    "session": None if record is None else record.to_dict(),
                }
            return {
                "sessions": [record.to_dict() for record in self.store.list_active()],
            }
        raise ValueError(f"unsupported operation: {operation}")

    def _submit(self, request: dict[str, object]) -> dict[str, object]:
        policy_raw = request.get("policy")
        if not isinstance(policy_raw, dict):
            raise ValueError("submit policy must be an object")
        policy = SessionPolicy(
            execution_mode=ExecutionMode(
                _required_text(policy_raw, "execution_mode").upper()
            ),
            access_scope=AccessScope(
                _required_text(policy_raw, "access_scope").upper()
            ),
            workload=Workload(_required_text(policy_raw, "workload").upper()),
            namespace=_optional_text(policy_raw, "namespace"),
            priority=int(policy_raw.get("priority", 0)),
            private_credits=int(policy_raw.get("private_credits", 1)),
        )
        record = self.store.submit(
            session_id=_required_text(request, "session_id"),
            owner_pid=_required_int(request, "owner_pid"),
            owner_token=_required_text(request, "owner_token"),
            owner_process_start=_optional_text(request, "owner_process_start"),
            owner_boot_id=_optional_text(request, "owner_boot_id"),
            test_node_id=_required_text(request, "test_node_id"),
            policy=policy,
            hard_deadline=float(request.get("hard_deadline", time.time() + 600.0)),
        )
        return {"session": record.to_dict()}

    def _transition(self, request: dict[str, object]) -> dict[str, object]:
        expected_raw = request.get("expected_version")
        expected_version = expected_raw if isinstance(expected_raw, int) else None
        record = self.store.transition(
            _required_text(request, "session_id"),
            _required_text(request, "owner_token"),
            SessionState(_required_text(request, "target").upper()),
            expected_version=expected_version,
            current_node=_optional_text(request, "current_node"),
            failure_token=_optional_text(request, "failure_token"),
        )
        return {"session": record.to_dict()}

    def _ownership(self, request: dict[str, object]) -> dict[str, object]:
        ownership_raw = request.get("ownership")
        if not isinstance(ownership_raw, dict):
            raise ValueError("ownership must be an object")
        page_ids_raw = ownership_raw.get("page_ids", [])
        if not isinstance(page_ids_raw, list) or not all(
            isinstance(item, str) for item in page_ids_raw
        ):
            raise ValueError("ownership.page_ids must be a string list")
        ownership = SessionOwnership(
            browser_context_id=_optional_text(ownership_raw, "browser_context_id"),
            page_ids=tuple(cast(list[str], page_ids_raw)),
            lease_id=_optional_text(ownership_raw, "lease_id"),
            runtime_id=_optional_text(ownership_raw, "runtime_id"),
        )
        record = self.store.set_ownership(
            _required_text(request, "session_id"),
            _required_text(request, "owner_token"),
            ownership,
        )
        return {"session": record.to_dict()}

    def _cleanup(self, request: dict[str, object]) -> dict[str, object]:
        receipt_raw = request.get("receipt")
        if not isinstance(receipt_raw, dict):
            raise ValueError("cleanup receipt must be an object")
        pages_raw = receipt_raw.get("closed_page_ids", [])
        if not isinstance(pages_raw, list) or not all(
            isinstance(item, str) for item in pages_raw
        ):
            raise ValueError("receipt.closed_page_ids must be a string list")
        receipt = CleanupReceipt(
            closed_page_ids=tuple(cast(list[str], pages_raw)),
            closed_context_id=_optional_text(receipt_raw, "closed_context_id"),
            released_lease_id=_optional_text(receipt_raw, "released_lease_id"),
            released_runtime_id=_optional_text(receipt_raw, "released_runtime_id"),
            ledger_cleaned=receipt_raw.get("ledger_cleaned") is True,
            sealed=receipt_raw.get("sealed") is True,
            requested_at=float(receipt_raw.get("requested_at", 0.0)),
            observed_at=float(receipt_raw.get("observed_at", 0.0)),
            completed_at=float(receipt_raw.get("completed_at", time.time())),
        )
        record = self.store.record_cleanup(
            _required_text(request, "session_id"),
            _required_text(request, "owner_token"),
            receipt,
        )
        return {"session": record.to_dict()}


class _CoordinatorServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True
    # The default socketserver backlog is 5. A normal SHARED launch burst can
    # therefore receive ECONNREFUSED before serve_forever drains the accept queue.
    request_queue_size = 128

    def __init__(self, path: Path, service: CoordinatorService) -> None:
        self.service = service
        self._ready = threading.Event()
        path = normalized_socket_path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.parent.chmod(0o700)
        path.unlink(missing_ok=True)
        super().__init__(str(path), _CoordinatorHandler)
        path.chmod(0o600)

    def server_activate(self) -> None:
        super().server_activate()
        self._ready.set()

    def wait_ready(self, timeout_sec: float = 5.0) -> bool:
        return self._ready.wait(timeout=timeout_sec)


class _CoordinatorHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        connection = cast(socket.socket, self.request)
        raw = bytearray()
        while len(raw) <= _MAX_REQUEST_BYTES:
            chunk = connection.recv(min(65_536, _MAX_REQUEST_BYTES + 1 - len(raw)))
            if not chunk:
                break
            raw.extend(chunk)
            if b"\n" in chunk:
                break
        response: dict[str, object]
        try:
            line = bytes(raw).split(b"\n", 1)[0]
            payload: object = json.loads(line.decode("utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("request must be a JSON object")
            server = cast(_CoordinatorServer, self.server)
            response = {"ok": True, **server.service.handle(payload)}
        except (ValueError, KeyError, PermissionError, json.JSONDecodeError) as exc:
            response = {
                "ok": False,
                "error": type(exc).__name__,
                "detail": str(exc),
            }
        connection.sendall(
            json.dumps(response, separators=(",", ":"), sort_keys=True).encode() + b"\n"
        )


def request(
    payload: dict[str, object],
    *,
    socket_path: Path | None = None,
    timeout_sec: float = 10.0,
) -> dict[str, object]:
    target = normalized_socket_path(socket_path or default_socket_path())
    deadline = time.monotonic() + max(0.1, timeout_sec)
    last_refused: ConnectionRefusedError | None = None
    while True:
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                connection.settimeout(remaining)
                connection.connect(str(target))
                connection.sendall(
                    json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
                    + b"\n"
                )
                raw = bytearray()
                while len(raw) <= _MAX_REQUEST_BYTES:
                    chunk = connection.recv(
                        min(65_536, _MAX_REQUEST_BYTES + 1 - len(raw))
                    )
                    if not chunk:
                        break
                    raw.extend(chunk)
                    if b"\n" in chunk:
                        break
            response: object = json.loads(bytes(raw).split(b"\n", 1)[0].decode("utf-8"))
            if not isinstance(response, dict):
                raise RuntimeError("coordinator returned a non-object response")
            if response.get("ok") is not True:
                raise RuntimeError(
                    f"DEV_GATE_COORDINATOR_ERROR: {response.get('detail', 'unknown error')}"
                )
            return response
        except ConnectionRefusedError as exc:
            last_refused = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(min(0.02, deadline - time.monotonic()))
    if last_refused is not None:
        raise last_refused
    raise TimeoutError("coordinator request timed out")


class _BackgroundReaper:
    """P0-A: coordinator-owned periodic store + hung/stale lease reap."""

    def __init__(self, service: CoordinatorService) -> None:
        self._service = service
        raw = os.environ.get("MYRM_DEV_GATE_BACKGROUND_REAP_SEC", "30").strip()
        try:
            self._interval_sec = max(5.0, float(raw))
        except ValueError:
            self._interval_sec = 30.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._interval_sec <= 0:
            return
        self._thread = threading.Thread(
            target=self._loop,
            name="dev-gate-background-reap",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _loop(self) -> None:
        os.environ["MYRM_DEV_GATE_COORDINATOR_REAP"] = "1"
        while not self._stop.wait(self._interval_sec):
            try:
                self._service.handle({"operation": "reap"})
                from e2e_stale_lease_reap import (  # noqa: PLC0415
                    maybe_reap_excess_wave_leases,
                    maybe_reap_hung_chrome_e2e_pytest,
                    maybe_reap_stale_heartbeat_leases,
                )

                maybe_reap_stale_heartbeat_leases()
                maybe_reap_hung_chrome_e2e_pytest()
                maybe_reap_excess_wave_leases()
            except Exception:
                pass


def serve(socket_path: Path, database_path: Path) -> None:
    socket_path = normalized_socket_path(socket_path)
    service = CoordinatorService(DevGateStore(database_path.resolve()))
    reaper = _BackgroundReaper(service)
    reaper.start()
    server = _CoordinatorServer(
        socket_path,
        service,
    )
    try:
        server.serve_forever(poll_interval=0.2)
    finally:
        reaper.stop()
        server.server_close()
        socket_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Myrm Dev Gate coordinator")
    parser.add_argument("command", choices=("serve", "request"))
    parser.add_argument("--socket", type=Path, default=default_socket_path())
    parser.add_argument("--database", type=Path, default=default_store_path())
    parser.add_argument("--payload", default="")
    args = parser.parse_args()
    if args.command == "serve":
        serve(args.socket, args.database)
        return 0
    payload: object = json.loads(args.payload)
    if not isinstance(payload, dict):
        raise ValueError("--payload must be a JSON object")
    print(json.dumps(request(payload, socket_path=args.socket), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
