"""MCP shim transport adapter — stdio JSON-RPC framing and process lifecycle.

[INPUT]
dev_gate.contract (POS: Dev Gate v2 合约常量 SSOT)
mux.transport_supervisor (POS: recovery budget / lock wait)

[OUTPUT]
TransportDeadError: transport 层统一异常
TrackedRLock: 可追踪持有者的可重入请求锁
transport constants: _TRANSPORT_RECOVER_ATTEMPTS, _MCP_READ_POLL_SEC 等

[POS]
从 chrome_mcp_client.py 提取的 transport 层基础设施。
TrackedRLock 保证并行场景下请求锁持有状态可观测，
TransportDeadError 统一所有 stdio 层失败为单一异常类型。
"""

from __future__ import annotations

import logging
import os
import threading

_LOGGER = logging.getLogger(__name__)

_TRANSPORT_RECOVER_ATTEMPTS = 3
_REQUEST_LOCK_ACQUIRE_SEC = 5.0
_REQUEST_LOCK_ACQUIRE_PARALLEL_CAP_SEC = 90.0
_REQUEST_LOCK_ACQUIRE_SIGNOFF_PARALLEL_CAP_SEC = 180.0
_EXPLICIT_SHORT_TOOL_TIMEOUT_CEILING_SEC = 30.0


class TransportDeadError(RuntimeError):
    """Raised when the MCP shim process is missing, exited, or its stdio pipe closed.

    All transport-level failures (_read EOF, _write BrokenPipe, process poll != None)
    MUST use this type so _request can catch and trigger _recover_mux_transport.
    Application-level errors (tool failures, protocol errors) use plain RuntimeError.
    """


class TrackedRLock:
    """Reentrant request lock with portable ownership state for orphan recovery."""

    __slots__ = ("_lock", "_state_lock", "_owner_thread_id", "_depth")

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._state_lock = threading.Lock()
        self._owner_thread_id: int | None = None
        self._depth = 0

    def acquire(self, blocking: bool = True, timeout: float = -1.0) -> bool:
        if not blocking:
            acquired = self._lock.acquire(blocking=False)
        elif timeout < 0:
            acquired = self._lock.acquire()
        else:
            acquired = self._lock.acquire(timeout=timeout)
        if not acquired:
            return False
        thread_id = threading.get_ident()
        with self._state_lock:
            if self._owner_thread_id is None:
                self._owner_thread_id = thread_id
            elif self._owner_thread_id != thread_id:
                self._lock.release()
                raise RuntimeError("request lock ownership state is inconsistent")
            self._depth += 1
        return True

    def release(self) -> None:
        thread_id = threading.get_ident()
        with self._state_lock:
            if self._owner_thread_id != thread_id or self._depth < 1:
                raise RuntimeError("cannot release an unowned request lock")
            self._depth -= 1
            if self._depth == 0:
                self._owner_thread_id = None
        self._lock.release()

    def locked(self) -> bool:
        with self._state_lock:
            return self._depth > 0


def parallel_request_lock_cap_sec() -> float:
    try:
        from dev_gate.contract import is_e2e_signoff_runtime

        if is_e2e_signoff_runtime():
            return _REQUEST_LOCK_ACQUIRE_SIGNOFF_PARALLEL_CAP_SEC
    except ImportError:
        pass
    return _REQUEST_LOCK_ACQUIRE_PARALLEL_CAP_SEC


def resolve_request_lock_acquire_sec(peer_count_fn: "callable[[], int]") -> float:
    """Scale per-session mux request lock wait with parallel E2E load (R76).

    ``transport_supervisor.recovery_lock_wait_sec`` scales on active pytest count;
    peer_count_fn scales on concurrent mux sessions.
    """
    scaled = _REQUEST_LOCK_ACQUIRE_SEC
    try:
        from mux.transport_supervisor import recovery_lock_wait_sec

        scaled = max(scaled, recovery_lock_wait_sec())
    except ImportError:
        pass
    peer_count = peer_count_fn()
    if peer_count > 1:
        peer_scaled = _REQUEST_LOCK_ACQUIRE_SEC + (peer_count - 1) * 15.0
        scaled = max(scaled, peer_scaled)
    return min(
        max(_REQUEST_LOCK_ACQUIRE_SEC, scaled),
        parallel_request_lock_cap_sec(),
    )


def chrome_e2e_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 9333
