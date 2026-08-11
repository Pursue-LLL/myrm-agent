"""Unix-socket coordinator for the recoverable Chrome E2E session registry."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import select
import socket
import socketserver
import tempfile
import threading
import time
from pathlib import Path
from typing import cast

from desktop_seat_controller import (
    DesktopSeatController,
    desktop_seat_capacity,
)
from dev_gate_async_queue import (
    DevGateAsyncWriter,
    async_queue_enabled,
    max_async_queue_depth,
)
from dev_gate_session import (
    AccessScope,
    CleanupReceipt,
    CleanupUnsealedError,
    ExecutionMode,
    SessionOwnership,
    SessionPolicy,
    SessionState,
    TerminalConflictError,
    Workload,
)
from dev_gate_store import DevGateStore, default_store_path
from private_resource_controller import (
    PrivateResourceController,
    private_capacity_credits,
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
        if operation == "list_active":
            operation = "snapshot"
        if operation == "reap":
            reaped = list(self.store.reap_abandoned())
            reaped.extend(self.store.reap_expired_deadlines())
            compacted = self.store.compact_journal()
            from idle_hygiene_scheduler import (
                run_idle_tab_hygiene_if_safe,
            )  # noqa: PLC0415

            hygiene = run_idle_tab_hygiene_if_safe(trigger="coordinator_reap")
            return {
                "reaped_session_ids": reaped,
                "journal_events_compacted": compacted,
                "idle_tab_hygiene": hygiene,
            }
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
        if operation == "destroy":
            record = self.store.destroy_ownership(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
            )
            return {"session": record.to_dict()}
        if operation == "cleanup":
            return self._cleanup(request)
        if operation == "teardown_finish":
            return self._teardown_finish(request)
        if operation == "finish":
            record = self.store.finish(
                _required_text(request, "session_id"),
                _required_text(request, "owner_token"),
                succeeded=request.get("succeeded") is True,
                failure_token=_optional_text(request, "failure_token"),
                pytest_evidence_hash=_optional_text(request, "pytest_evidence_hash"),
            )
            from idle_hygiene_scheduler import (
                run_idle_tab_hygiene_if_safe,
            )  # noqa: PLC0415

            hygiene = run_idle_tab_hygiene_if_safe(trigger="coordinator_finish")
            return {"session": record.to_dict(), "idle_tab_hygiene": hygiene}
        if operation == "private_admit":
            self.store.reap_abandoned()
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
        if operation == "wait_event":
            event_types_raw = request.get("event_types")
            if not isinstance(event_types_raw, list) or not all(
                isinstance(item, str) and item.strip() for item in event_types_raw
            ):
                raise ValueError(
                    "wait_event.event_types must be a non-empty string list"
                )
            after_raw = request.get("after_event_id")
            after_event_id = int(after_raw) if isinstance(after_raw, int) else 0
            budget_raw = request.get("budget_sec")
            budget_sec = (
                float(budget_raw) if isinstance(budget_raw, (int, float)) else 30.0
            )
            from dev_gate_event_wait import (
                SessionEventTimeoutError,
                wait_for_session_event,
            )
            from dev_gate_event_hub import (
                coordinator_event_hub,
                wait_for_session_event_subscribed,
            )

            hub = coordinator_event_hub()
            wait_fn = wait_for_session_event_subscribed
            if os.environ.get("MYRM_DEV_GATE_EVENT_SUBSCRIBE", "1").strip().lower() in {
                "0",
                "false",
                "no",
                "off",
            }:
                wait_fn = wait_for_session_event  # type: ignore[assignment]

            try:
                if wait_fn is wait_for_session_event_subscribed:
                    event = wait_for_session_event_subscribed(
                        self.store,
                        hub,
                        session_id=_required_text(request, "session_id"),
                        event_types=frozenset(str(item) for item in event_types_raw),
                        after_event_id=after_event_id,
                        budget_sec=budget_sec,
                    )
                else:
                    event = wait_for_session_event(
                        self.store,
                        session_id=_required_text(request, "session_id"),
                        event_types=frozenset(str(item) for item in event_types_raw),
                        after_event_id=after_event_id,
                        budget_sec=budget_sec,
                    )
            except SessionEventTimeoutError:
                self.private_controller.sweep_stale_credits()
                return {"event": None, "timed_out": True}
            return {"event": event, "timed_out": False}
        if operation == "snapshot":
            session_id = _optional_text(request, "session_id")
            if session_id == "__health__":
                health: dict[str, object] = {}
                try:
                    from host_resource_governor import (  # noqa: PLC0415
                        host_resource_governor_snapshot,
                        recent_transition_log,
                    )

                    health["hostGovernor"] = host_resource_governor_snapshot()
                    health["hostGovernorTransitions"] = recent_transition_log(limit=8)
                except ImportError:
                    pass
                try:
                    from dev_gate_status import dev_gate_status  # noqa: PLC0415

                    health["devGate"] = dev_gate_status()
                except ImportError:
                    pass
                return health
            if session_id:
                record = self.store.get(session_id)
                return {
                    "session": None if record is None else record.to_dict(),
                }
            return {
                "sessions": [record.to_dict() for record in self.store.list_active()],
            }
        if operation == "export_signoff_artifact":
            output_raw = request.get("output_path")
            if not isinstance(output_raw, str) or not output_raw.strip():
                raise ValueError("export_signoff_artifact.output_path is required")
            session_limit_raw = request.get("session_limit")
            event_limit_raw = request.get("event_limit")
            session_limit = (
                int(session_limit_raw) if isinstance(session_limit_raw, int) else 200
            )
            event_limit = (
                int(event_limit_raw) if isinstance(event_limit_raw, int) else 2000
            )
            session_ids_raw = request.get("session_ids")
            session_ids: tuple[str, ...] | None = None
            if isinstance(session_ids_raw, list):
                session_ids = tuple(
                    item.strip()
                    for item in session_ids_raw
                    if isinstance(item, str) and item.strip()
                )
            from dev_gate_signoff_export import export_signoff_artifact  # noqa: PLC0415

            return export_signoff_artifact(
                self.store,
                Path(output_raw.strip()),
                session_ids=session_ids,
                session_limit=session_limit,
                event_limit=event_limit,
            )
        if operation == "verify_signoff_artifact":
            path_raw = request.get("output_path")
            if not isinstance(path_raw, str) or not path_raw.strip():
                raise ValueError("verify_signoff_artifact.output_path is required")
            from dev_gate_signoff_export import verify_signoff_artifact  # noqa: PLC0415

            return verify_signoff_artifact(Path(path_raw.strip()))
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
        session_id = _required_text(request, "session_id")
        owner_token = _required_text(request, "owner_token")
        expected_raw = request.get("expected_version")
        expected_version = expected_raw if isinstance(expected_raw, int) else None
        merge_page_raw = request.get("merge_page_id")
        if isinstance(merge_page_raw, str) and merge_page_raw.strip():
            if expected_version is None:
                raise ValueError("merge_page_id requires expected_version")
            record = self.store.cas_add_page_id(
                session_id,
                owner_token,
                merge_page_raw.strip(),
                expected_version=expected_version,
            )
            return {"session": record.to_dict()}
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
            session_id,
            owner_token,
            ownership,
            expected_version=expected_version,
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
            physical_released=(
                True
                if receipt_raw.get("physical_released") is True
                else (False if receipt_raw.get("physical_released") is False else None)
            ),
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

    def _teardown_finish(self, request: dict[str, object]) -> dict[str, object]:
        receipt_raw = request.get("receipt")
        if not isinstance(receipt_raw, dict):
            raise ValueError("teardown_finish receipt must be an object")
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
            physical_released=(
                True
                if receipt_raw.get("physical_released") is True
                else (False if receipt_raw.get("physical_released") is False else None)
            ),
            sealed=receipt_raw.get("sealed") is True,
            requested_at=float(receipt_raw.get("requested_at", 0.0)),
            observed_at=float(receipt_raw.get("observed_at", 0.0)),
            completed_at=float(receipt_raw.get("completed_at", time.time())),
        )
        record = self.store.teardown_and_finish(
            _required_text(request, "session_id"),
            _required_text(request, "owner_token"),
            receipt,
            succeeded=request.get("succeeded") is True,
            failure_token=_optional_text(request, "failure_token"),
            pytest_evidence_hash=_optional_text(request, "pytest_evidence_hash"),
        )
        from idle_hygiene_scheduler import run_idle_tab_hygiene_if_safe  # noqa: PLC0415

        hygiene = run_idle_tab_hygiene_if_safe(trigger="coordinator_teardown_finish")
        return {"session": record.to_dict(), "idle_tab_hygiene": hygiene}


class _CoordinatorServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True
    # The default socketserver backlog is 5. A normal SHARED launch burst can
    # therefore receive ECONNREFUSED before serve_forever drains the accept queue.
    request_queue_size = 128

    def __init__(self, path: Path, service: CoordinatorService) -> None:
        self.service = service
        self._async_writer: DevGateAsyncWriter | None = None
        if async_queue_enabled():
            self._async_writer = DevGateAsyncWriter(
                service,
                max_queue=max_async_queue_depth(),
            )
            self._async_writer.start()
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
            if server._async_writer is not None:
                body = server._async_writer.dispatch(payload)
            else:
                body = server.service.handle(payload)
                from dev_gate_event_hub import notify_write_result  # noqa: PLC0415

                notify_write_result(payload, body)
            if (
                payload.get("operation") == "snapshot"
                and server._async_writer is not None
            ):
                body = {
                    **body,
                    "asyncQueueDepth": server._async_writer.queue_depth,
                }
            response = {"ok": True, **body}
        except (
            ValueError,
            KeyError,
            PermissionError,
            json.JSONDecodeError,
            TerminalConflictError,
            CleanupUnsealedError,
        ) as exc:
            response = {
                "ok": False,
                "error": type(exc).__name__,
                "detail": str(exc),
            }
        try:
            connection.sendall(
                json.dumps(response, separators=(",", ":"), sort_keys=True).encode()
                + b"\n"
            )
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass


def _recv_until_newline(
    connection: socket.socket,
    *,
    deadline: float,
    max_bytes: int,
) -> bytes:
    """Read one newline-terminated response with select() hard deadline (R-coordinator-zombie)."""
    raw = bytearray()
    while len(raw) <= max_bytes:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("coordinator request timed out")
        readable, _, _ = select.select([connection], [], [], remaining)
        if not readable:
            raise TimeoutError("coordinator request timed out")
        chunk = connection.recv(min(65_536, max_bytes + 1 - len(raw)))
        if not chunk:
            break
        raw.extend(chunk)
        if b"\n" in chunk:
            break
    return bytes(raw)


def request(
    payload: dict[str, object],
    *,
    socket_path: Path | None = None,
    timeout_sec: float = 10.0,
) -> dict[str, object]:
    target = normalized_socket_path(socket_path or default_socket_path())
    deadline = time.monotonic() + max(0.1, timeout_sec)
    last_refused: ConnectionRefusedError | None = None
    last_decode: json.JSONDecodeError | None = None
    last_timeout: TimeoutError | None = None
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
                raw = _recv_until_newline(
                    connection,
                    deadline=deadline,
                    max_bytes=_MAX_REQUEST_BYTES,
                )
            if not raw:
                raise json.JSONDecodeError("empty coordinator response", "", 0)
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
        except json.JSONDecodeError as exc:
            last_decode = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(min(0.05, deadline - time.monotonic()))
        except TimeoutError as exc:
            last_timeout = exc
            if time.monotonic() >= deadline:
                break
            time.sleep(min(0.02, deadline - time.monotonic()))
    if last_decode is not None:
        raise RuntimeError(
            f"DEV_GATE_COORDINATOR_ERROR: {last_decode.msg}"
        ) from last_decode
    if last_refused is not None:
        raise last_refused
    if last_timeout is not None:
        raise last_timeout
    raise TimeoutError("coordinator request timed out")


_DEADLINE_REAP_GRACE_SEC = 5.0


def _terminate_deadline_reaped(
    store: DevGateStore,
    reaped_session_ids: list[object],
) -> None:
    """P0-A enforcement: terminate owner processes of deadline-expired sessions.

    Only kills when PID + process_start still match the original owner,
    preventing PID-reuse misfire.
    """
    import signal  # noqa: PLC0415

    from owner_identity import owner_process_matches  # noqa: PLC0415

    for raw_id in reaped_session_ids:
        session_id = str(raw_id)
        record = store.get(session_id)
        if record is None:
            continue
        if record.failure_token != "HARD_DEADLINE":
            continue
        pid = record.owner_pid
        process_start = record.owner_process_start
        if pid <= 0:
            continue
        if not owner_process_matches(pid=pid, expected_start=process_start):
            continue
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
        time.sleep(_DEADLINE_REAP_GRACE_SEC)
        if not owner_process_matches(pid=pid, expected_start=process_start):
            continue
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


class _BackgroundReaper:
    """P0-A: coordinator-owned periodic store reap + stale wave leases (no peer SIGINT)."""

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
                result = self._service.handle({"operation": "reap"})
                _terminate_deadline_reaped(
                    self._service.store,
                    result.get("reaped_session_ids", []),
                )
                from e2e_stale_lease_reap import (  # noqa: PLC0415
                    maybe_reap_epoch_drift_stale_sessions,
                    maybe_reap_excess_wave_leases,
                    maybe_reap_hung_chrome_e2e_pytest,
                    maybe_reap_orphan_shared_backends,
                    maybe_reap_stale_empty_mux_contexts,
                    maybe_reap_stale_heartbeat_leases,
                )

                maybe_reap_stale_heartbeat_leases()
                maybe_reap_stale_empty_mux_contexts()
                maybe_reap_excess_wave_leases()
                maybe_reap_hung_chrome_e2e_pytest()
                maybe_reap_epoch_drift_stale_sessions()
                maybe_reap_orphan_shared_backends()
            except Exception:
                pass


def _acquire_serve_singleton_lock(database_path: Path) -> int:
    """Exclusive non-blocking flock — second serve exits immediately (TAB-8)."""
    lock_path = database_path.with_name(f"{database_path.name}.serve.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        os.close(fd)
        raise SystemExit(
            "DEV_GATE_COORDINATOR_SINGLETON: another serve instance holds the lock"
        ) from exc
    return fd


def serve(socket_path: Path, database_path: Path) -> None:
    socket_path = normalized_socket_path(socket_path)
    resolved_db = database_path.resolve()
    lock_fd = _acquire_serve_singleton_lock(resolved_db)
    from dev_gate_cli import _write_coordinator_code_stamp  # noqa: PLC0415

    _write_coordinator_code_stamp(resolved_db)
    service = CoordinatorService(DevGateStore(resolved_db))
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
        fcntl.flock(lock_fd, fcntl.LOCK_UN)
        os.close(lock_fd)


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
