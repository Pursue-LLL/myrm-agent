"""Browser Orchestrator Python client.

[INPUT]
Browser Orchestrator daemon (Unix socket JSON-RPC)

[OUTPUT]
BrowserOrchestratorClient: session/page lifecycle operations via daemon socket

[POS]
Python 侧与 Browser Orchestrator daemon 通信的唯一入口。
替代 chrome_mcp_client.py 中通过 subprocess 管理 MCP shim 进程的机制。
所有浏览器操作（create context, new page, close page, cleanup）
通过 Unix socket JSON 协议路由到 daemon，daemon 持有唯一 CDP 连接。
"""

from __future__ import annotations

import json
import logging
import os
import socket
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TypedDict

_LOGGER = logging.getLogger(__name__)

# Socket read budget = openPageTransaction wall + fair-scheduler grace (R299).
_ORCHESTRATOR_SCHEDULER_GRACE_SEC = 30.0
_SIGNOFF_TRUTHY = frozenset({"1", "true", "yes", "on"})


def orchestrator_open_tx_wall_sec() -> float:
    """Whole-RPC openPageTransaction wall — must match browser-orchestrator daemon default."""
    from dev_gate_contract import (  # noqa: PLC0415
        DEV_OPEN_PAGE_TRANSACTION_WALL_SEC,
        SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC,
    )

    if os.environ.get("E2E_SIGNOFF", "").strip().lower() in _SIGNOFF_TRUTHY:
        return float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC)
    raw_ms = os.environ.get("BROWSER_ORCHESTRATOR_OPEN_TX_WALL_MS", "").strip()
    if raw_ms:
        try:
            parsed_ms = int(raw_ms)
        except ValueError:
            parsed_ms = 0
        if parsed_ms > 0:
            return float(parsed_ms) / 1000.0
    raw_sec = os.environ.get("BROWSER_ORCHESTRATOR_OPEN_TX_WALL_SEC", "").strip()
    if raw_sec:
        try:
            parsed_sec = float(raw_sec)
        except ValueError:
            parsed_sec = 0.0
        if parsed_sec > 0:
            return parsed_sec
    return float(DEV_OPEN_PAGE_TRANSACTION_WALL_SEC)


def orchestrator_socket_timeout_cap_sec() -> float:
    """Return socket read cap aligned with openPageTransaction wall (no 480s retry storm)."""
    wall = orchestrator_open_tx_wall_sec()
    burst_lanes = 0
    for key in ("MYRM_E2E_PHASE_C_BURST_LANES", "MYRM_E2E_PARALLEL_ACTIVE_LEASES"):
        raw = os.environ.get(key, "").strip()
        try:
            count = int(raw)
        except ValueError:
            continue
        if count >= 2:
            burst_lanes = max(burst_lanes, count)
    queue_headroom = 15.0 * float(max(0, burst_lanes - 1))
    return wall + _ORCHESTRATOR_SCHEDULER_GRACE_SEC + queue_headroom


def _default_socket_path() -> str:
    runtime = os.environ.get("XDG_RUNTIME_DIR", "").strip()
    if not runtime:
        runtime = os.path.join(tempfile.gettempdir(), f"mux-{os.getuid()}")
    return str(Path(runtime) / "browser-orchestrator.sock")


_SOCKET_PATH = os.environ.get("BROWSER_ORCHESTRATOR_SOCKET", _default_socket_path())
_REQUEST_TIMEOUT_SEC = 30.0
_CONNECT_TIMEOUT_SEC = 5.0


class SessionResult(TypedDict):
    contextId: str


class PageResult(TypedDict):
    pageId: int
    targetId: str


class OpenPageTransactionResult(TypedDict):
    pageId: int
    targetId: str
    url: str


class CloseResult(TypedDict):
    closed: bool


class CleanupSealResult(TypedDict):
    sessionId: str
    sealed: bool
    pendingTargets: list[str]
    closedTargets: list[str]
    failedTargets: list[str]


class OrchestratorStatus(TypedDict):
    state: str
    generation: int
    contexts: int
    scheduler: dict[str, int]
    recovery: dict[str, object]


class BrowserOrchestratorClient:
    """Synchronous client for the Browser Orchestrator daemon."""

    def __init__(
        self,
        socket_path: str | None = None,
        timeout_sec: float = _REQUEST_TIMEOUT_SEC,
    ) -> None:
        self._socket_path = socket_path or _SOCKET_PATH
        self._timeout_sec = timeout_sec
        self._next_id = 1

    @contextmanager
    def bounded_request_timeout(self, timeout_sec: float) -> Iterator[None]:
        """Temporarily cap socket read budget (orphan recovery must not block 180s+)."""
        prior = self._timeout_sec
        self._timeout_sec = min(prior, max(5.0, timeout_sec))
        try:
            yield
        finally:
            self._timeout_sec = prior

    @contextmanager
    def elevated_request_timeout(self, timeout_sec: float) -> Iterator[None]:
        """Raise socket read budget up to orchestrator cap (parallel open_page queue)."""
        prior = self._timeout_sec
        cap = orchestrator_socket_timeout_cap_sec()
        self._timeout_sec = min(cap, max(prior, max(5.0, timeout_sec)))
        try:
            yield
        finally:
            self._timeout_sec = prior

    def create_session(self, session_id: str) -> SessionResult:
        """Create a new isolated BrowserContext for the given session."""
        from chrome_e2e.gates.lease_gate import assert_orchestrator_lease_allowed

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {"sessionId": session_id}
        if lease_id:
            params["leaseId"] = lease_id
        result = self._request("session/create", params)
        return SessionResult(contextId=result["contextId"])

    def destroy_session(self, session_id: str) -> CleanupSealResult:
        """Destroy session: close all pages, dispose context, return seal."""
        result = self._request("session/destroy", {"sessionId": session_id})
        return CleanupSealResult(
            sessionId=session_id,
            sealed=result.get("sealed", False),
            pendingTargets=result.get("pendingTargets", []),
            closedTargets=result.get("closedTargets", []),
            failedTargets=result.get("failedTargets", []),
        )

    def create_page(self, session_id: str, url: str = "") -> PageResult:
        """Create a new page in the session's BrowserContext."""
        from chrome_e2e.gates.lease_gate import assert_orchestrator_lease_allowed

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {"sessionId": session_id, "url": url}
        if lease_id:
            params["leaseId"] = lease_id
        result = self._request("page/create", params)
        return PageResult(pageId=result["pageId"], targetId=result["targetId"])

    def open_page_transaction(
        self,
        session_id: str,
        *,
        url: str,
        binding_expression: str | None = None,
    ) -> OpenPageTransactionResult:
        """Atomically open a page: background create → optional inject → navigate."""
        from chrome_e2e.gates.lease_gate import assert_orchestrator_lease_allowed

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {"sessionId": session_id, "url": url}
        if lease_id:
            params["leaseId"] = lease_id
        if binding_expression is not None:
            params["bindingExpression"] = binding_expression
        result = self._request("page/openTransaction", params)
        return OpenPageTransactionResult(
            pageId=int(result["pageId"]),
            targetId=str(result["targetId"]),
            url=str(result.get("url", url)),
        )

    def close_page(self, session_id: str, target_id: str) -> CloseResult:
        """Close a specific page by target ID."""
        result = self._request(
            "page/close", {"sessionId": session_id, "targetId": target_id}
        )
        return CloseResult(closed=result.get("closed", False))

    def navigate_page(
        self, session_id: str, target_id: str, url: str
    ) -> dict[str, object]:
        """Navigate an owned page to ``url``."""
        result = self._request(
            "page/navigate",
            {"sessionId": session_id, "targetId": target_id, "url": url},
        )
        return {"ok": bool(result.get("ok", False))}

    def evaluate_page(
        self,
        session_id: str,
        target_id: str,
        expression: str,
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        """Evaluate JavaScript in an owned page."""
        prior_timeout = self._timeout_sec
        cdp_sec: float | None = None
        if timeout_sec is not None:
            cdp_sec = min(max(5.0, timeout_sec), 180.0)
            self._timeout_sec = min(
                orchestrator_socket_timeout_cap_sec(),
                cdp_sec + _ORCHESTRATOR_SCHEDULER_GRACE_SEC,
            )
        try:
            payload: dict[str, object] = {
                "sessionId": session_id,
                "targetId": target_id,
                "expression": expression,
            }
            if cdp_sec is not None:
                payload["timeoutMs"] = int(cdp_sec * 1000)
            result = self._request(
                "page/evaluate",
                payload,
            )
        finally:
            self._timeout_sec = prior_timeout
        return {"value": result.get("value")}

    def cleanup_seal(self, session_id: str) -> CleanupSealResult | None:
        """Verify cleanup seal: check if all targets are physically absent."""
        result = self._request("cleanup/seal", {"sessionId": session_id})
        if result is None:
            return None
        return CleanupSealResult(
            sessionId=session_id,
            sealed=result.get("sealed", False),
            pendingTargets=result.get("pendingTargets", []),
            closedTargets=result.get("closedTargets", []),
            failedTargets=result.get("failedTargets", []),
        )

    def status(self) -> OrchestratorStatus:
        """Get daemon status snapshot."""
        result = self._request("status", {})
        return OrchestratorStatus(
            state=result.get("state", "UNKNOWN"),
            generation=result.get("generation", 0),
            contexts=result.get("contexts", 0),
            scheduler=result.get("scheduler", {}),
            recovery=result.get("recovery", {}),
        )

    def is_alive(self) -> bool:
        """Check if daemon is reachable and not in FAILED state."""
        try:
            snapshot = self.status()
            state = str(snapshot.get("state", "")).strip()
            return state not in ("", "UNKNOWN", "FAILED")
        except (OSError, TimeoutError, RuntimeError):
            return False

    def _request(self, method: str, params: dict[str, object]) -> dict[str, object]:
        req_id = self._next_id
        self._next_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        )

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self._connect_timeout_sec)
        try:
            sock.connect(self._socket_path)
        except (FileNotFoundError, ConnectionRefusedError) as exc:
            sock.close()
            raise RuntimeError(
                f"Browser Orchestrator daemon not running: {exc}"
            ) from exc

        sock.settimeout(self._timeout_sec)
        try:
            sock.sendall((payload + "\n").encode())
            return self._read_response(sock, req_id)
        finally:
            sock.close()

    def _read_response(
        self, sock: socket.socket, expected_id: int
    ) -> dict[str, object]:
        buf = b""
        deadline = time.monotonic() + self._timeout_sec
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sock.settimeout(min(remaining, 5.0))
            try:
                chunk = sock.recv(65536)
            except TimeoutError:
                continue
            if not chunk:
                break
            buf += chunk
            nl = buf.find(b"\n")
            if nl >= 0:
                line = buf[:nl].decode()
                return self._parse_response(line, expected_id)

        raise TimeoutError(
            f"Browser Orchestrator response timeout ({self._timeout_sec}s)"
        )

    def _parse_response(self, line: str, expected_id: int) -> dict[str, object]:
        try:
            msg = json.loads(line)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Malformed response from Browser Orchestrator: {line[:200]}"
            ) from exc

        if msg.get("id") != expected_id:
            raise RuntimeError(
                f"Response ID mismatch: expected {expected_id}, got {msg.get('id')}"
            )
        if "error" in msg:
            err = msg["error"]
            raise RuntimeError(f"Browser Orchestrator error: {err.get('message', err)}")
        return msg.get("result", {})

    @property
    def _connect_timeout_sec(self) -> float:
        return min(_CONNECT_TIMEOUT_SEC, self._timeout_sec)
