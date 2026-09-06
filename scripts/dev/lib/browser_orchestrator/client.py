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
import select
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TypedDict

_LOGGER = logging.getLogger(__name__)

# Socket read budget = openPageTransaction wall + fair-scheduler grace (R299).
_ORCHESTRATOR_SCHEDULER_GRACE_SEC = 30.0
_SIGNOFF_TRUTHY = frozenset({"1", "true", "yes", "on"})
_WAVE_LEASE_CACHE_TTL_SEC = 5.0
_wave_lease_cache: tuple[float, int] | None = None
_socket_timeout_cap_cache: tuple[float, tuple[float, int], float] | None = None
_SOCKET_TIMEOUT_CAP_CACHE_TTL_SEC = 5.0

# fix#14 (§24 W3e): daemon respawn serialization — at most one spawn per window
# so a parallel ConnectionRefused storm never produces a subprocess spawn storm.
_DAEMON_RESPAWN_COOLDOWN_SEC = 8.0
_daemon_respawn_last_at: float = 0.0
_DAEMON_READY_WALL_SEC = 60.0
_daemon_unreachable_markers = (
    "daemon not running",
    "connection refused",
    "connection closed before response",
    "connection lost",
    "connection reset",
    "browser orchestrator response timeout",
)
_REPLAY_SAFE_METHODS = frozenset(
    {
        "session/create",
        "session/destroy",
        "page/close",
        "cleanup/seal",
        "scheduler/setEffectiveCredits",
    }
)


def _daemon_unreachable_message(message: str) -> bool:
    lowered = message.lower()
    return any(marker in lowered for marker in _daemon_unreachable_markers)


def _request_failed_before_send(message: str) -> bool:
    """Return true only for connect failures where the RPC was never written."""
    lowered = message.lower()
    return "daemon not running" in lowered or "connection refused" in lowered


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _try_claim_daemon_respawn() -> bool:
    """Atomically claim the respawn slot; True when this lane may spawn."""
    global _daemon_respawn_last_at
    now = time.monotonic()
    if now - _daemon_respawn_last_at < _DAEMON_RESPAWN_COOLDOWN_SEC:
        return False
    _daemon_respawn_last_at = now
    return True


def spawn_ensure_orchestrator() -> None:
    """Best-effort daemon (re)start via the ensure script (flock-serialized)."""
    script = _monorepo_root() / "scripts/dev/ensure-browser-orchestrator.sh"
    if not script.is_file():
        _LOGGER.warning("orchestrator ensure script missing: %s", script)
        return
    env = os.environ.copy()
    env["MYRM_BROWSER_ORCHESTRATOR"] = "1"
    env["MYRM_BROWSER_ORCHESTRATOR_ENSURE_DONE"] = "1"
    node_dir = "/opt/homebrew/bin"
    path = env.get("PATH", "")
    if node_dir not in path:
        from e2e_core.real_user_home import real_user_home  # noqa: PLC0415

        bun_bin = str(real_user_home() / ".bun/bin")
        env["PATH"] = f"{node_dir}:{bun_bin}:{path}"
    try:
        subprocess.run(
            ["bash", str(script)],
            env=env,
            timeout=45.0,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        _LOGGER.warning("orchestrator respawn failed: %s", exc)


def _wait_daemon_ready(daemon: "BrowserOrchestratorClient") -> None:
    """Wait until the daemon reports READY (new generation)."""
    deadline = time.monotonic() + _DAEMON_READY_WALL_SEC
    while time.monotonic() < deadline:
        if daemon.is_ready():
            return
        time.sleep(0.5)
    raise RuntimeError(
        "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running after respawn — "
        "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
    )


def _parallel_load_from_env() -> int:
    burst_lanes = 0
    for key in (
        "MYRM_E2E_PARALLEL_ACTIVE_LEASES",
        "MYRM_E2E_PHASE_C_BURST_LANES",
        "MYRM_E2E_PARALLEL_ACTIVE_COUNT",
    ):
        raw = os.environ.get(key, "").strip()
        if raw.isdigit():
            burst_lanes = max(burst_lanes, int(raw))
    return burst_lanes


def _cached_parallel_load() -> int:
    """Env-first parallel load — never block evaluate hot path on wave.sh."""
    global _wave_lease_cache
    env_load = _parallel_load_from_env()
    if env_load >= 2:
        return env_load
    now = time.monotonic()
    if _wave_lease_cache is not None:
        cached_at, cached = _wave_lease_cache
        if now - cached_at < _WAVE_LEASE_CACHE_TTL_SEC:
            return cached
    load = 0
    try:
        from e2e_core.peer_count_ssot import parallel_active_test_count_ssot

        load = parallel_active_test_count_ssot()
    except ImportError:
        load = _wave_lease_count_probe()
    _wave_lease_cache = (now, load)
    return load


def _parallel_scaled_evaluate_timeout_sec(base: float) -> float:
    """Scale orchestrator CDP evaluate under parallel chrome_e2e mux queue (R124)."""
    load = _cached_parallel_load()
    if load < 2:
        return base
    return min(180.0, base + float(load) * 15.0)


def _wave_lease_count_probe() -> int:
    try:
        from e2e_core.stack_mutation_policy import wave_active_lease_count

        root = Path(__file__).resolve().parents[5]
        return wave_active_lease_count(root)
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


def orchestrator_open_tx_wall_sec() -> float:
    """Whole-RPC openPageTransaction wall — must match browser-orchestrator daemon default."""
    from dev_gate.contract import (  # noqa: PLC0415
        DEV_OPEN_PAGE_TRANSACTION_WALL_SEC,
        SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC,
    )

    raw_ms = os.environ.get("BROWSER_ORCHESTRATOR_OPEN_TX_WALL_MS", "").strip()
    if raw_ms:
        try:
            parsed_ms = int(raw_ms)
        except ValueError:
            parsed_ms = 0
        if parsed_ms > 0:
            return float(parsed_ms) / 1000.0
    if os.environ.get("E2E_SIGNOFF", "").strip().lower() in _SIGNOFF_TRUTHY:
        return float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC)
    return float(DEV_OPEN_PAGE_TRANSACTION_WALL_SEC)


def orchestrator_socket_timeout_cap_sec() -> float:
    """Return socket read cap aligned with openPageTransaction wall (no 480s retry storm)."""
    global _socket_timeout_cap_cache
    wall = orchestrator_open_tx_wall_sec()
    burst_lanes = _parallel_load_from_env()
    if burst_lanes < 2:
        burst_lanes = max(burst_lanes, _cached_parallel_load())
    cache_key = (wall, burst_lanes)
    now = time.monotonic()
    if _socket_timeout_cap_cache is not None:
        cached_at, cached_key, cached = _socket_timeout_cap_cache
        if (
            cached_key == cache_key
            and now - cached_at < _SOCKET_TIMEOUT_CAP_CACHE_TTL_SEC
        ):
            return cached
    queue_headroom = 15.0 * float(max(0, burst_lanes - 1))
    cap = wall + _ORCHESTRATOR_SCHEDULER_GRACE_SEC + queue_headroom
    _socket_timeout_cap_cache = (now, cache_key, cap)
    return cap


def _socket_cap_from_operation_budgets(raw: object) -> float:
    """Translate daemon operation/queue budgets into one whole-RPC socket cap."""
    if not isinstance(raw, dict):
        return 0.0
    grace_raw = raw.get("schedulerGraceMs", _ORCHESTRATOR_SCHEDULER_GRACE_SEC * 1000)
    grace_ms = float(grace_raw) if isinstance(grace_raw, (int, float)) and grace_raw > 0 else 30_000.0
    candidates: list[float] = []
    for key in ("operationTimeoutMs", "queueWaitMs"):
        values = raw.get(key)
        if not isinstance(values, dict):
            continue
        for value in values.values():
            if isinstance(value, (int, float)) and value > 0:
                candidates.append(float(value) + grace_ms)
    return max(candidates, default=0.0) / 1000.0


def _default_socket_path() -> str:
    """Stable socket path independent of TMPDIR.

    TMPDIR is repointed by myrm dev isolation (e.g. detach spawns a private
    tmp.XXXX dir) while the daemon may be started by a sibling process with a
    different TMPDIR — so a tmpdir-derived socket path silently splits the pair
    into two worlds. Anchor on the real user home, same directory that holds
    ``daemon.pid``.
    """
    from e2e_core.real_user_home import real_user_home  # noqa: PLC0415

    return str(
        real_user_home()
        / ".local/state/myrm-browser-orchestrator"
        / "browser-orchestrator.sock"
    )


_SOCKET_PATH = os.environ.get("BROWSER_ORCHESTRATOR_SOCKET", _default_socket_path())
_REQUEST_TIMEOUT_SEC = 30.0
_CONNECT_TIMEOUT_SEC = 5.0
_MAX_SOCKET_MESSAGE_BYTES = 1_048_576


class SessionResult(TypedDict):
    contextId: str


class PageResult(TypedDict):
    pageId: int
    targetId: str


class OpenPageTransactionResult(TypedDict):
    pageId: int
    targetId: str
    url: str


class OpenAppRouteResult(TypedDict):
    pageId: int
    targetId: str
    url: str
    hydrated: bool


class CloseResult(TypedDict):
    closed: bool


class CleanupSealResult(TypedDict):
    sessionId: str
    sealed: bool
    pendingTargets: list[str]
    closedTargets: list[str]
    failedTargets: list[str]
    contextId: str
    contextReleased: bool
    physicalReleased: bool


class OrchestratorStatus(TypedDict):
    state: str
    generation: int
    contexts: int
    scheduler: dict[str, int]
    recovery: dict[str, object]
    capabilities: list[str]
    operationBudgets: dict[str, object]


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
        self._id_lock = threading.Lock()
        self._operation_budget_cache: tuple[float, float] | None = None

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
        cap = self.socket_timeout_cap_sec()
        requested = max(5.0, timeout_sec)
        # A caller-provided budget may intentionally exceed the daemon's
        # advertised minimum. Elevation must never shorten that budget.
        self._timeout_sec = max(prior, min(cap, requested))
        try:
            yield
        finally:
            self._timeout_sec = prior

    def adopt_operation_budget_timeout(self) -> float:
        """Raise this client's socket budget to the running daemon contract."""
        cap = self.socket_timeout_cap_sec()
        self._timeout_sec = max(self._timeout_sec, cap)
        return cap

    def socket_timeout_cap_sec(self) -> float:
        """Return a socket cap that covers every advertised daemon budget."""
        fallback = orchestrator_socket_timeout_cap_sec()
        cached = self._operation_budget_cache
        now = time.monotonic()
        if cached is not None and now - cached[0] < _SOCKET_TIMEOUT_CAP_CACHE_TTL_SEC:
            return max(fallback, cached[1])
        try:
            snapshot = self.status()
        except (OSError, RuntimeError, TimeoutError, TypeError):
            return fallback
        cap = _socket_cap_from_operation_budgets(snapshot.get("operationBudgets"))
        self._operation_budget_cache = (now, cap)
        return max(fallback, cap)

    def create_session(self, session_id: str) -> SessionResult:
        """Create a new isolated BrowserContext for the given session."""
        from chrome_e2e.gates.lease_gate import (
            assert_orchestrator_lease_allowed,
            validated_wave_state_file,
        )

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {"sessionId": session_id}
        if lease_id:
            params["leaseId"] = lease_id
        params["waveStateFile"] = str(validated_wave_state_file())
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
            contextId=str(result.get("contextId", "")),
            contextReleased=bool(result.get("contextReleased", False)),
            physicalReleased=bool(result.get("physicalReleased", False)),
        )

    def create_page(self, session_id: str, url: str = "") -> PageResult:
        """Create a new page in the session's BrowserContext."""
        from chrome_e2e.gates.lease_gate import (
            assert_orchestrator_lease_allowed,
            validated_wave_state_file,
        )

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {"sessionId": session_id, "url": url}
        if lease_id:
            params["leaseId"] = lease_id
        params["waveStateFile"] = str(validated_wave_state_file())
        result = self._request("page/create", params)
        return PageResult(pageId=result["pageId"], targetId=result["targetId"])

    def open_app_route(
        self,
        session_id: str,
        *,
        url: str,
        shell_path: str,
        hydration_probe: str | None = None,
        hydrate_timeout_sec: float | None = None,
        binding_expression: str | None = None,
    ) -> OpenAppRouteResult:
        """Atomically create an isolated app route, bind, navigate, and hydrate.

        §19.11.10 NAV-2: single operation credit, single transaction. Every page
        is created in the session BrowserContext; the daemon injects the
        same-origin binding, navigates the subroute, then polls the RouteManifest
        hydration probe until ready or deadline.
        """
        from chrome_e2e.gates.lease_gate import (
            assert_orchestrator_lease_allowed,
            validated_wave_state_file,
        )

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {
            "sessionId": session_id,
            "url": url,
            "shellPath": shell_path,
        }
        if hydration_probe and hydration_probe.strip():
            params["hydrationProbe"] = hydration_probe
        if hydrate_timeout_sec is not None:
            params["hydrateTimeoutMs"] = int(hydrate_timeout_sec * 1000)
        if binding_expression and binding_expression.strip():
            params["bindingExpression"] = binding_expression
        if lease_id:
            params["leaseId"] = lease_id
        params["waveStateFile"] = str(validated_wave_state_file())
        prior_timeout = self._timeout_sec
        # Hydration wait lives inside the daemon RPC — give the socket budget
        # headroom above the hydration deadline (scheduler grace + poll granularity).
        deadline_sec = float(hydrate_timeout_sec or 60.0)
        self._timeout_sec = min(
            max(prior_timeout, deadline_sec + _ORCHESTRATOR_SCHEDULER_GRACE_SEC + 10.0),
            self.socket_timeout_cap_sec(),
        )
        try:
            result = self._request("page/openAppRoute", params)
        finally:
            self._timeout_sec = prior_timeout
        return OpenAppRouteResult(
            pageId=int(result["pageId"]),
            targetId=str(result["targetId"]),
            url=str(result.get("url", url)),
            hydrated=bool(result.get("hydrated", False)),
        )

    def open_page_transaction(
        self,
        session_id: str,
        *,
        url: str,
        binding_expression: str | None = None,
    ) -> OpenPageTransactionResult:
        """Atomically open a page: background create → optional inject → navigate."""
        from chrome_e2e.gates.lease_gate import (
            assert_orchestrator_lease_allowed,
            validated_wave_state_file,
        )

        lease_id = assert_orchestrator_lease_allowed()
        params: dict[str, object] = {"sessionId": session_id, "url": url}
        if lease_id:
            params["leaseId"] = lease_id
        params["waveStateFile"] = str(validated_wave_state_file())
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
        await_promise: bool = True,
        intent: str | None = None,
    ) -> dict[str, object]:
        """Evaluate JavaScript in an owned page (§24 W3b intent scoped budget)."""
        prior_timeout = self._timeout_sec
        cdp_sec: float | None = None
        if timeout_sec is not None:
            bounded = min(max(5.0, timeout_sec), 180.0)
            if bounded <= 20.0:
                cdp_sec = bounded
            else:
                cdp_sec = _parallel_scaled_evaluate_timeout_sec(bounded)
            self._timeout_sec = min(
                max(prior_timeout, cdp_sec + _ORCHESTRATOR_SCHEDULER_GRACE_SEC),
                self.socket_timeout_cap_sec(),
            )
        try:
            payload: dict[str, object] = {
                "sessionId": session_id,
                "targetId": target_id,
                "expression": expression,
                "awaitPromise": await_promise,
            }
            if cdp_sec is not None:
                payload["timeoutMs"] = int(cdp_sec * 1000)
            if intent:
                payload["intent"] = intent
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
            contextId=str(result.get("contextId", "")),
            contextReleased=bool(result.get("contextReleased", False)),
            physicalReleased=bool(result.get("physicalReleased", False)),
        )

    def status(self) -> OrchestratorStatus:
        """Get daemon status snapshot (never triggers daemon respawn)."""
        result = self._request("status", {}, allow_daemon_recovery=False)
        raw_budgets = result.get("operationBudgets")
        operation_budgets = (
            dict(raw_budgets) if isinstance(raw_budgets, dict) else {}
        )
        self._operation_budget_cache = (
            time.monotonic(),
            _socket_cap_from_operation_budgets(operation_budgets),
        )
        return OrchestratorStatus(
            state=result.get("state", "UNKNOWN"),
            generation=result.get("generation", 0),
            contexts=result.get("contexts", 0),
            scheduler=result.get("scheduler", {}),
            recovery=result.get("recovery", {}),
            capabilities=[str(cap) for cap in result.get("capabilities", [])],
            operationBudgets=operation_budgets,
        )

    def set_effective_credits(self, credits: int) -> int:
        """Bind Host Governor output to the daemon's live fair scheduler."""
        if not 1 <= credits <= 4:
            raise ValueError("credits must be between 1 and 4")
        result = self._request(
            "scheduler/setEffectiveCredits",
            {"credits": credits},
            allow_daemon_recovery=False,
        )
        effective = result.get("effectiveCredits")
        if not isinstance(effective, int):
            raise RuntimeError("orchestrator did not acknowledge effective credits")
        return effective

    def supports_open_app_route(self) -> bool:
        """True when the daemon exposes the atomic ``page/openAppRoute`` RPC (NAV-2)."""
        try:
            return "openAppRoute" in self.status().get("capabilities", [])
        except (OSError, TimeoutError, RuntimeError):
            return False

    def is_alive(self) -> bool:
        """Check if daemon is reachable and not in FAILED state."""
        try:
            snapshot = self.status()
            state = str(snapshot.get("state", "")).strip()
            return state not in ("", "UNKNOWN", "FAILED")
        except (OSError, TimeoutError, RuntimeError):
            return False

    def is_ready(self) -> bool:
        """Check if the daemon is reachable and accepts browser operations."""
        try:
            return str(self.status().get("state", "")).strip() == "READY"
        except (OSError, TimeoutError, RuntimeError):
            return False

    def reset_failure_latch_if_idle(self) -> dict[str, object]:
        """UBDP-H §27.6: clear FAILED latch when daemon owns no contexts/ops."""
        return self._request(
            "admin/resetFailureLatch",
            {},
            allow_daemon_recovery=False,
        )

    def _request(
        self,
        method: str,
        params: dict[str, object],
        *,
        allow_daemon_recovery: bool = True,
    ) -> dict[str, object]:
        with self._id_lock:
            req_id = self._next_id
            self._next_id += 1
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        )
        try:
            return self._request_raw(payload, req_id)
        except (OSError, RuntimeError) as exc:
            message = str(exc)
            if not allow_daemon_recovery or not _daemon_unreachable_message(message):
                raise
            if method not in _REPLAY_SAFE_METHODS and not _request_failed_before_send(
                message
            ):
                raise RuntimeError(
                    "BROWSER_OPERATION_RESULT_UNKNOWN: request may have reached "
                    f"daemon; method={method}; cause={message}"
                ) from exc
            self._recover_daemon_generation()
            return self._request_raw(payload, req_id)

    def _request_raw(self, payload: str, req_id: int) -> dict[str, object]:
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

    def _recover_daemon_generation(self) -> None:
        """Respawn a crashed/replaced daemon once per cooldown, then wait ready.

        fix#14 (§24 W3e): a parallel ConnectionRefused storm must not crash every
        lane nor spawn a subprocess storm — the module-level watchdog cooldown
        serializes respawn while this lane waits for the new generation.
        """
        if not _try_claim_daemon_respawn():
            _wait_daemon_ready(self)
            return
        spawn_ensure_orchestrator()
        _wait_daemon_ready(self)

    def _read_response(
        self, sock: socket.socket, expected_id: int
    ) -> dict[str, object]:
        buf = b""
        deadline = time.monotonic() + self._timeout_sec
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            wait_sec = min(remaining, 5.0)
            try:
                if sock.fileno() < 0:
                    raise RuntimeError(
                        "Browser Orchestrator connection closed before response"
                    )
            except OSError as exc:
                raise RuntimeError(
                    "Browser Orchestrator connection closed before response"
                ) from exc
            readable, _, _ = select.select([sock], [], [], wait_sec)
            if not readable:
                continue
            try:
                chunk = sock.recv(65536)
            except OSError as exc:
                raise RuntimeError(
                    f"Browser Orchestrator connection lost: {exc}"
                ) from exc
            if not chunk:
                raise RuntimeError(
                    "Browser Orchestrator connection closed before response"
                )
            buf += chunk
            if len(buf) > _MAX_SOCKET_MESSAGE_BYTES:
                raise RuntimeError("Browser Orchestrator response too large")
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
