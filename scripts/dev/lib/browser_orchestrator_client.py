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
from pathlib import Path
from typing import TypedDict

_LOGGER = logging.getLogger(__name__)


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

    def create_session(self, session_id: str) -> SessionResult:
        """Create a new isolated BrowserContext for the given session."""
        result = self._request("session/create", {"sessionId": session_id})
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
        result = self._request("page/create", {"sessionId": session_id, "url": url})
        return PageResult(pageId=result["pageId"], targetId=result["targetId"])

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
        self, session_id: str, target_id: str, expression: str
    ) -> dict[str, object]:
        """Evaluate JavaScript in an owned page."""
        result = self._request(
            "page/evaluate",
            {
                "sessionId": session_id,
                "targetId": target_id,
                "expression": expression,
            },
        )
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
