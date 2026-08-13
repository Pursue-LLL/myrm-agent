"""Synchronous Chrome DevTools MCP mux client for formal UI E2E runners.

[INPUT]
chrome_mcp_errors (POS: MCP 错误分类谓词)
mcp_protocol (POS: JSON-RPC 解析与 tool 响应提取)
mcp_page_lease_heartbeat (POS: page lease 心跳管理)
cdp_chat_support (POS: E2E API/chat 消息 SSOT)
dev_gate_contract (POS: Dev Gate v2 合约常量 SSOT)
dev_gate_cli (POS: Unix socket 协调器自动启动客户端)
mux_load (POS: mux context / wave lease 负载探针)
mux_upstream_admission (POS: mux cold attach 准入)
browser_orchestrator_client (POS: Browser Orchestrator daemon Unix socket JSON-RPC 客户端)

[OUTPUT]
ChromeMcpClient: 同步 MCP JSON-RPC 客户端（shim 进程管理、transport recovery、generation check、page lease；MYRM_BROWSER_ORCHESTRATOR=1 时通过 daemon 分发）
McpPage: MCP 页面句柄（targetId + client 引用）
_TransportDeadError: transport 层统一异常（_read EOF / _write BrokenPipe / 进程退出）

[POS]
正式 pytest UI E2E 的 MCP JSON-RPC 通信层。管理 shim 子进程生命周期，
提供 transport-level 容错（_TransportDeadError → recover）、generation-based 竞态防护、
page lease 心跳，供 mcp_chat_ui / cdp_chat_* 调用。
MYRM_BROWSER_ORCHESTRATOR=1 时条件分发到 Browser Orchestrator daemon。
"""

from __future__ import annotations

import json
import logging
import os
import select
import shutil
import subprocess
import threading
import time
import uuid
from builtins import BaseExceptionGroup, ExceptionGroup
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit

from browser_orchestrator import browser_operation_credit_slot
from cdp_chat.support import (
    e2e_runtime_binding,
    e2e_runtime_binding_source,
    e2e_runtime_bootstrap_apply_js,
    wait_e2e_provider_ready,
)
from chrome_mcp.errors import (
    is_benign_cleanup_error as _is_benign_cleanup_error,
)
from chrome_mcp.errors import (
    is_context_reset_error as is_context_reset_error,
)
from chrome_mcp.errors import (
    is_page_ownership_error as is_page_ownership_error,
)
from chrome_mcp.errors import (
    is_page_ownership_error_message as _is_page_ownership_error,
)
from chrome_mcp.errors import (
    is_transient_mux_error as _is_transient_mux_error,
)
from dev_gate.contract import (
    LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
    MUX_RECLAIM_STALL_TOKEN,
    NEW_PAGE_TOOL_RETRY_ATTEMPTS,
    TOOL_RETRY_ATTEMPTS,
)
from chrome_mcp.page_helpers import (
    _STALE_MUX_PAGE_TOKEN,
)
from chrome_mcp.page_helpers import (
    ensure_cdp_ready_before_parallel_new_page as _ensure_cdp_ready_before_parallel_new_page,
)
from chrome_mcp.page_helpers import (
    http_close_exact_target as _http_close_exact_target,
)
from chrome_mcp.page_helpers import (
    is_mux_parallel_fail_fast_message as _is_mux_parallel_fail_fast_message,
)
from chrome_mcp.page_helpers import (
    is_new_page_cdp_drift_message as _is_new_page_cdp_drift_message,
)
from chrome_mcp.page_helpers import (
    is_retryable_new_page_parse_exc as _is_retryable_new_page_parse_exc,
)
from chrome_mcp.page_helpers import (
    new_page_retry_attempts as _new_page_retry_attempts,
)
from chrome_mcp.page_helpers import (
    new_page_tool_max_attempts as _new_page_tool_max_attempts,
)
from chrome_mcp.page_helpers import (
    parallel_mux_peer_count as _parallel_mux_peer_count,
)
from chrome_mcp.page_helpers import (
    parallel_scaled_page_timeout_ms as _parallel_scaled_page_timeout_ms,
)
from chrome_mcp.page_helpers import (
    reclaim_wall_deadline as _reclaim_wall_deadline,
)
from chrome_mcp.page_helpers import (
    recover_new_page_chrome_drift as _recover_new_page_chrome_drift,
)
from chrome_mcp.page_helpers import (
    remaining_reclaim_sec as _remaining_reclaim_sec,
)
from chrome_mcp.page_helpers import (
    shim_process_alive as _shim_process_alive,
)
from chrome_mcp.page_helpers import (
    should_recover_mux_after_tool_error as _should_recover_mux_after_tool_error,
)
from chrome_mcp.page_helpers import (
    tool_retry_attempts as _tool_retry_attempts,
)
from chrome_mcp.page_helpers import (
    tool_retry_backoff_sec as _tool_retry_backoff_sec,
)
from chrome_mcp.page_helpers import (
    wave_command_timeout_sec as _wave_command_timeout_sec,
)
from chrome_mcp.page_lease_heartbeat import PageLeaseHeartbeat
from chrome_mcp.protocol import (
    parse_evaluate_result,
    parse_new_page,
    text_content,
)
from mux.transport_adapter import (
    _TRANSPORT_RECOVER_ATTEMPTS,
)
from mux.transport_adapter import (
    TrackedRLock as _TrackedRLock,
)
from mux.transport_adapter import (
    TransportDeadError as _TransportDeadError,
)
from mux.transport_adapter import (
    resolve_request_lock_acquire_sec as _resolve_request_lock_acquire_sec_raw,
)
from mux.load import (
    MuxLoadSnapshot,
    adaptive_page_timeout_ms,
    adaptive_tool_timeout_sec,
    snapshot_mux_load,
)

_CLEANUP_TIMEOUT_SEC = 15.0
_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC = LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC
_MCP_READ_POLL_SEC = _LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC
_TOOL_RETRY_ATTEMPTS = TOOL_RETRY_ATTEMPTS
_NEW_PAGE_TOOL_RETRY_ATTEMPTS = NEW_PAGE_TOOL_RETRY_ATTEMPTS
_PAGE_LEASE_TTL_SEC = int(os.environ.get("MYRM_PAGE_LEASE_TTL_SEC", "600"))
_PAGE_LEASE_HEARTBEAT_INTERVAL_SEC = 30.0
_EXPLICIT_SHORT_TOOL_TIMEOUT_CEILING_SEC = 30.0
_LOGGER = logging.getLogger(__name__)


def _resolve_request_lock_acquire_sec() -> float:
    return _resolve_request_lock_acquire_sec_raw(_parallel_mux_peer_count)


@dataclass(frozen=True, slots=True)
class McpPage:
    page_id: int
    target_id: str
    lease_id: str
    context_id: str | None = None
    url: str | None = None


class ChromeMcpClient:
    """One mux context. Every page is paired with an exact Wave READ lease."""

    def __init__(self, *, request_timeout_sec: float = 180.0) -> None:
        self._request_timeout_sec = request_timeout_sec
        self._process: subprocess.Popen[str] | None = None
        self._request_id = 0
        self._request_generation = self._initial_mux_generation()
        self._request_lock = _TrackedRLock()
        self._stderr_lines: deque[str] = deque(maxlen=100)
        self._stderr_thread: threading.Thread | None = None
        self._pages: dict[int, McpPage] = {}
        self._disconnected_pages: dict[int, McpPage] = {}
        self._page_lease_heartbeat = PageLeaseHeartbeat(
            self._heartbeat_lease,
            interval_sec=_PAGE_LEASE_HEARTBEAT_INTERVAL_SEC,
        )
        lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
        self._browser_context_id = (
            f"orch-{lease_id}"
            if lease_id
            else os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
            or os.environ.get("MYRM_E2E_RUN_ID", "").strip()
            or f"myrm-{os.getpid()}-{uuid.uuid4().hex}"
        )
        self._agent_id = (
            os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
            or os.environ.get("MYRM_WAVE_AGENT_ID", "").strip()
            or f"pytest-mcp:{os.getpid()}:{uuid.uuid4().hex}"
        )
        self._parent_lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
        self._monorepo_root = Path(__file__).resolve().parents[5]
        self._wave = self._monorepo_root / "myrm-agent/scripts/dev/wave.sh"
        self._mux_load_cache: MuxLoadSnapshot | None = None
        self._reclaim_in_progress = False
        self._mux_eval_executor: object | None = None
        self._mux_reset_executor: object | None = None
        self._tool_wall_deadline: float | None = None
        self._cold_shim_recover_streak = 0
        self._use_daemon = (
            os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1"
        )
        self._daemon_client: BrowserOrchestratorClient | None = None
        self._daemon_session_id: str | None = None
        self._unpublished_target_ids: set[str] = set()

    def _track_unpublished_target(self, target_id: str) -> None:
        tid = target_id.strip()
        if tid:
            self._unpublished_target_ids.add(tid)

    def _commit_unpublished_target(self, target_id: str) -> None:
        self._unpublished_target_ids.discard(target_id.strip())

    def _abort_unpublished_targets(self, *, keep: frozenset[str] = frozenset()) -> None:
        if not self._unpublished_target_ids:
            return
        from browser_orchestrator.page_create_transaction import (
            close_exact_unpublished_targets,
        )  # noqa: PLC0415

        closed, failed = close_exact_unpublished_targets(
            self._unpublished_target_ids,
            keep=keep,
        )
        if closed or failed:
            print(
                f"PAGE_CREATE_ABORT: closed={closed} failed={failed} "
                f"remaining={len(self._unpublished_target_ids)}",
                flush=True,
            )
        return self._request_lock.locked()

    def _require_daemon_alive(self, client: BrowserOrchestratorClient) -> None:
        if not client.is_alive():
            raise RuntimeError(
                "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running — "
                "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
            )

    def _ensure_daemon_session(self) -> BrowserOrchestratorClient:
        """Lazily create daemon client and session; idempotent."""
        if self._daemon_client is not None:
            self._require_daemon_alive(self._daemon_client)
            return self._daemon_client
        from browser_orchestrator.client import BrowserOrchestratorClient

        client = BrowserOrchestratorClient(timeout_sec=self._request_timeout_sec)
        self._require_daemon_alive(client)
        session_id = self._browser_context_id
        client.create_session(session_id)
        self._daemon_client = client
        self._daemon_session_id = session_id
        _LOGGER.info("daemon session created: %s", session_id)
        return client

    def _destroy_daemon_session(self) -> None:
        """Destroy daemon session if active; best-effort."""
        client = self._daemon_client
        session_id = self._daemon_session_id
        if client is None or session_id is None:
            return
        try:
            result = client.destroy_session(session_id)
            _LOGGER.info(
                "daemon session destroyed: %s sealed=%s",
                session_id,
                result.get("sealed"),
            )
        except (OSError, RuntimeError, TimeoutError) as exc:
            _LOGGER.warning("daemon session destroy failed: %s", exc)
        finally:
            self._daemon_client = None
            self._daemon_session_id = None

    @staticmethod
    def _daemon_open_page_retryable(message: str) -> bool:
        lowered = message.lower()
        return (
            "cdp evaluate failed" in lowered
            or "cdp request timeout" in lowered
            or "browser orchestrator response timeout" in lowered
            or "does not own target" in lowered
            or "no target with given id" in lowered
            or "no context for session" in lowered
            or "e2e_user_closed_tab" in lowered
            or "openpagetransaction wall timeout" in lowered
            or "session with given id not found" in lowered
        )

    def _daemon_open_page_fast_create(
        self,
        client: BrowserOrchestratorClient,
        session_id: str,
        url: str,
        *,
        binding_expression: str | None = None,
        max_attempts: int = 3,
    ) -> dict[str, object]:
        """create blank → optional SHPOIB inject → navigate (avoids openPageTransaction queue stalls)."""
        last_exc: BaseException | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                if attempt > 1:
                    self._destroy_daemon_session()
                    client = self._ensure_daemon_session()
                    session_id = self._daemon_session_id
                    assert session_id is not None
                created = client.create_page(session_id, url="about:blank")
                target_id = str(created["targetId"])
                page_id = int(created["pageId"])
                if binding_expression:
                    client.evaluate_page(
                        session_id,
                        target_id,
                        binding_expression,
                        timeout_sec=30.0,
                    )
                target_url = url.strip()
                if target_url and target_url != "about:blank":
                    client.navigate_page(session_id, target_id, target_url)
                return {
                    "pageId": page_id,
                    "targetId": target_id,
                    "url": target_url or url,
                }
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_exc = exc
                if (
                    not self._daemon_open_page_retryable(str(exc))
                    or attempt >= max_attempts
                ):
                    break
                time.sleep(min(2.0 * float(attempt), 6.0))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("daemon open page fast create failed without exception")

    def _daemon_new_page(self, url: str) -> McpPage:
        client = self._ensure_daemon_session()
        session_id = self._daemon_session_id
        assert session_id is not None
        lease_id = self._acquire_page_lease()
        try:
            runtime_binding = self._runtime_binding_source_for(url)
            last_exc: BaseException | None = None
            for attempt in range(1, 4):
                try:
                    if runtime_binding:
                        source, _expected = runtime_binding
                        binding_expression = f"(() => {{{source} return true; }})()"
                    else:
                        binding_expression = None
                    try:
                        result = self._daemon_open_page_fast_create(
                            client,
                            session_id,
                            url,
                            binding_expression=binding_expression,
                        )
                    except (TimeoutError, OSError, RuntimeError) as fast_exc:
                        if not self._daemon_open_page_retryable(str(fast_exc)):
                            raise
                        if binding_expression is None:
                            raise
                        result = client.open_page_transaction(
                            session_id,
                            url=url,
                            binding_expression=binding_expression,
                        )
                    page_id = result["pageId"]
                    target_id = result["targetId"]
                    page = McpPage(
                        page_id=page_id,
                        target_id=target_id,
                        lease_id=lease_id,
                        context_id=session_id,
                        url=result.get("url", url),
                    )
                    self._pages[page_id] = page
                    self._page_lease_heartbeat.track(lease_id)
                    return page
                except (TimeoutError, OSError, RuntimeError) as exc:
                    last_exc = exc
                    message = str(exc).lower()
                    retryable = self._daemon_open_page_retryable(message)
                    if not retryable or attempt >= 3:
                        raise
                    if (
                        "does not own target" in message
                        or "no target with given id" in message
                        or "no context for session" in message
                        or "e2e_user_closed_tab" in message
                    ):
                        self._destroy_daemon_session()
                        client = self._ensure_daemon_session()
                        session_id = self._daemon_session_id
                        assert session_id is not None
                    time.sleep(min(2.0 * float(attempt), 4.0))
            if last_exc is not None:
                raise last_exc
            raise RuntimeError("daemon new_page failed without exception")
        except Exception:
            try:
                self._release_lease(lease_id, close_wave_if_idle=False)
            except (RuntimeError, TimeoutError) as release_exc:
                if not _is_benign_cleanup_error(str(release_exc)):
                    _LOGGER.warning(
                        "daemon new_page cleanup release failed: %s",
                        release_exc,
                    )
            raise

    def _daemon_evaluate(
        self,
        page: McpPage,
        expression: str,
        *,
        timeout_sec: float = 15.0,
        await_promise: bool = True,
    ) -> object:
        client = self._ensure_daemon_session()
        session_id = self._daemon_session_id
        assert session_id is not None
        result = client.evaluate_page(
            session_id,
            page.target_id,
            expression,
            timeout_sec=timeout_sec,
            await_promise=await_promise,
        )
        return result.get("value")

    def _daemon_navigate(self, page: McpPage, url: str) -> None:
        client = self._ensure_daemon_session()
        session_id = self._daemon_session_id
        assert session_id is not None
        client.navigate_page(session_id, page.target_id, url)

    def _daemon_close_page(self, page: McpPage, *, ignore_errors: bool = False) -> None:
        self._page_lease_heartbeat.untrack(page.lease_id)
        client = self._daemon_client
        session_id = self._daemon_session_id
        if client is None or session_id is None:
            self._pages.pop(page.page_id, None)
            try:
                self._release_page_lease(page, unbind=True)
            except (RuntimeError, TimeoutError):
                _LOGGER.warning("daemon lease release failed (no client)")
            return
        try:
            client.close_page(session_id, page.target_id)
        except (OSError, RuntimeError, TimeoutError) as exc:
            if not ignore_errors:
                raise RuntimeError(f"daemon close_page failed: {exc}") from exc
            _LOGGER.warning("daemon close_page failed (ignored): %s", exc)
        self._pages.pop(page.page_id, None)
        self._disconnected_pages.pop(page.page_id, None)
        try:
            self._release_page_lease(page, unbind=True)
        except (RuntimeError, TimeoutError) as exc:
            if not ignore_errors:
                raise
            _LOGGER.warning("daemon lease release failed: %s", exc)

    @staticmethod
    def _initial_mux_generation() -> int:
        """Bind client generation to runtime cell ledger when SHPOIB slot is active."""
        try:
            from e2e_core.runtime_cell import current_cell_id, read_cell_mux_generation

            if current_cell_id():
                return max(0, read_cell_mux_generation())
        except ImportError:
            pass
        return 0

    def mux_eval_executor(self) -> object:
        """Dedicated pool for mux evaluate — avoids default asyncio pool exhaustion."""
        if self._mux_eval_executor is None:
            from concurrent.futures import ThreadPoolExecutor

            self._mux_eval_executor = ThreadPoolExecutor(
                max_workers=4,
                thread_name_prefix="myrm-mux-eval",
            )
        return self._mux_eval_executor

    def mux_reset_executor(self) -> object:
        """Separate single-worker pool so reset never queues behind hung evaluate threads."""
        if self._mux_reset_executor is None:
            from concurrent.futures import ThreadPoolExecutor

            self._mux_reset_executor = ThreadPoolExecutor(
                max_workers=2,
                thread_name_prefix="myrm-mux-reset",
            )
        return self._mux_reset_executor

    def discard_mux_reset_executor(self) -> None:
        """Drop a hung reset worker so the next orphan recover can submit immediately."""
        old = self._mux_reset_executor
        self._mux_reset_executor = None
        if old is not None:
            old.shutdown(wait=False, cancel_futures=True)

    def _acquire_request_lock(
        self, *, timeout_sec: float | None = None
    ) -> _TrackedRLock:
        max_wait_sec = _resolve_request_lock_acquire_sec()
        wait_sec = float(timeout_sec) if timeout_sec is not None else max_wait_sec
        if timeout_sec is not None:
            wait_sec = min(max_wait_sec, max(0.01, wait_sec))
        else:
            wait_sec = max(0.1, min(wait_sec, max_wait_sec))
        # R184: open-page budget must cap mux lock wait — orphan to_thread otherwise
        # holds the lock past asyncio wall timeout under parallel signoff load.
        if self._tool_wall_deadline is not None:
            wall_remaining = self.remaining_tool_wall_sec()
            if wall_remaining is not None and wall_remaining <= 0:
                raise TimeoutError(
                    "Chrome MCP request lock wall budget exhausted "
                    f"(cap={wait_sec:.1f}s)"
                )
            if wall_remaining is not None:
                wait_sec = min(wait_sec, wall_remaining)
        lock = self._request_lock
        if not lock.acquire(timeout=wait_sec):
            raise RuntimeError(
                f"{MUX_RECLAIM_STALL_TOKEN}: request lock blocked for {wait_sec:.1f}s"
            )
        return lock

    def _release_request_lock(self, lock: _TrackedRLock | None = None) -> None:
        target = lock if lock is not None else self._request_lock
        try:
            target.release()
        except RuntimeError:
            # abandon_inflight_requests() may replace _request_lock while orphan
            # threads still hold the previous lock instance.
            pass

    def _request_lock_is_held(self) -> bool:
        return self._request_lock.locked()

    def _read_wave_status(self) -> dict[str, object] | None:
        try:
            result = subprocess.run(
                ["bash", str(self._wave), "status"],
                cwd=str(self._monorepo_root),
                capture_output=True,
                text=True,
                timeout=min(_wave_command_timeout_sec(), 15.0),
                check=False,
                env=os.environ.copy(),
            )
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode != 0:
            return None
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _mux_load_snapshot(self) -> MuxLoadSnapshot:
        if self._mux_load_cache is not None:
            age = time.monotonic() - self._mux_load_cache.captured_at
            if age < 2.0:
                return self._mux_load_cache
        probe = snapshot_mux_load()
        if probe.mux_contexts >= 2:
            wave_status = self._read_wave_status()
            snapshot = snapshot_mux_load(wave_status=wave_status, force=True)
        else:
            snapshot = probe
        self._mux_load_cache = snapshot
        return snapshot

    def _resolve_trsm_mode(self) -> "TransportRecoveryMode":
        from mux.transport_recovery_core import (
            TransportRecoveryMode,
            resolve_transport_recovery_mode,
        )

        try:
            from dev_gate.contract import is_e2e_signoff_runtime

            if (
                is_e2e_signoff_runtime()
                and not self._pages
                and not self._disconnected_pages
            ):
                return TransportRecoveryMode.SOLO_FULL
        except ImportError:
            pass
        return resolve_transport_recovery_mode(
            parallel_peers=_parallel_mux_peer_count(),
            shim_alive=_shim_process_alive(self),
        )

    def set_tool_wall_deadline(self, deadline: float | None) -> None:
        """Hard monotonic deadline for in-flight tool retries (open_mcp_page budget)."""
        self._tool_wall_deadline = deadline

    def remaining_tool_wall_sec(self) -> float | None:
        """Monotonic seconds left on open-page tool wall, or None when unset (R184)."""
        if self._tool_wall_deadline is None:
            return None
        return max(0.0, self._tool_wall_deadline - time.monotonic())

    def _open_page_budget_active(self) -> bool:
        return self._tool_wall_deadline is not None

    def _check_tool_wall_deadline(self, phase: str) -> None:
        if self._tool_wall_deadline is None:
            return
        if time.monotonic() >= self._tool_wall_deadline:
            raise TimeoutError(f"Chrome MCP {phase} wall budget exhausted")

    def _default_page_timeout_ms(self) -> int:
        load = self._mux_load_snapshot()
        return adaptive_page_timeout_ms(
            mux_contexts=load.mux_contexts,
            wave_leases=load.wave_leases,
        )

    def _resolve_tool_timeout_sec(
        self,
        timeout_sec: float | None,
        *,
        page_timeout_ms: int | None = None,
    ) -> float:
        load = self._mux_load_snapshot()
        adaptive = adaptive_tool_timeout_sec(
            mux_contexts=load.mux_contexts,
            wave_leases=load.wave_leases,
            page_timeout_ms=page_timeout_ms,
        )
        if timeout_sec is None:
            return adaptive
        if timeout_sec <= self._request_timeout_sec:
            return min(timeout_sec, adaptive)
        return max(timeout_sec, adaptive)

    def _page_tool_timeout_sec(self, page_timeout_ms: int) -> float:
        """Align navigate/new_page tool timeout with page timeout under open-page budget (R228)."""
        page_sec = page_timeout_ms / 1000.0 + 5.0
        if self._open_page_budget_active():
            return self._resolve_tool_timeout_sec(
                page_sec,
                page_timeout_ms=page_timeout_ms,
            )
        return self._resolve_tool_timeout_sec(
            min(page_sec, self._request_timeout_sec),
            page_timeout_ms=page_timeout_ms,
        )

    def __enter__(self) -> ChromeMcpClient:
        self.start()
        return self

    def __exit__(self, _exc_type: object, exc: object, _traceback: object) -> None:
        try:
            self.close()
        except Exception as cleanup_error:
            if isinstance(exc, BaseException):
                raise BaseExceptionGroup(
                    "Chrome MCP test and cleanup both failed",
                    [exc, cleanup_error],
                ) from None
            raise

    def start(self) -> None:
        if self._use_daemon:
            from browser_orchestrator.client import BrowserOrchestratorClient

            client = BrowserOrchestratorClient(timeout_sec=self._request_timeout_sec)
            self._require_daemon_alive(client)
            return
        from chrome_e2e.gates.entry_guard import assert_chrome_mcp_mux_entry_allowed

        assert_chrome_mcp_mux_entry_allowed()
        process = self._process
        if process is not None and process.poll() is None:
            return
        if process is not None:
            self._teardown_shim_process()
        self._spawn_shim_process()
        self._initialize_shim_session()

    def close(self) -> None:
        errors: list[Exception] = []
        self._abort_unpublished_targets()
        if self._request_lock_is_held():
            _LOGGER.warning(
                "Chrome MCP close detected held request lock; abandon in-flight requests first"
            )
            try:
                self.abandon_inflight_requests()
            except Exception as exc:  # pragma: no cover - best effort cleanup path
                errors.append(exc)
        self._page_lease_heartbeat.stop()
        pages_to_close = list(
            {
                page.page_id: page
                for page in (
                    list(self._pages.values()) + list(self._disconnected_pages.values())
                )
            }.values()
        )
        for page in pages_to_close:
            try:
                self.close_page(page, ignore_errors=True)
            except Exception as exc:
                errors.append(exc)
        if self._use_daemon:
            try:
                self._destroy_daemon_session()
            except Exception as exc:
                errors.append(exc)
            if errors:
                raise ExceptionGroup("Chrome MCP cleanup failed", errors)
            return
        process = self._process
        self._process = None
        if process is not None:
            try:
                if process.stdin is not None:
                    process.stdin.close()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=3)
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise ExceptionGroup("Chrome MCP cleanup failed", errors)

    @staticmethod
    def _runtime_binding_source_for(url: str) -> tuple[str, dict[str, object]] | None:
        source = e2e_runtime_binding_source()
        binding = e2e_runtime_binding()
        if source is None or binding is None:
            return None
        target = urlsplit(url)
        ui = urlsplit(str(binding["uiOrigin"]))
        if (target.scheme, target.hostname, target.port) != (
            ui.scheme,
            ui.hostname,
            ui.port,
        ):
            return None
        return source, binding

    def _bind_and_navigate_runtime_page(
        self,
        page: McpPage,
        url: str,
        binding: tuple[str, dict[str, object]],
        *,
        timeout_ms: int,
    ) -> None:
        source, expected = binding
        api_base = str(expected.get("apiBase") or "").strip()
        bootstrap_timeout_sec = max(30.0, min(120.0, timeout_ms / 1000.0))
        provider_wait_sec = max(60.0, bootstrap_timeout_sec)
        if api_base and not wait_e2e_provider_ready(
            api_url=api_base, timeout_sec=provider_wait_sec
        ):
            raise RuntimeError(
                "E2E_RUNTIME_BINDING_FAILED: "
                f"private API not ready before binding: {api_base}"
            )
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        last_observed: dict[str, object] | str | None = None
        shpoib_parallel = os.environ.get("MYRM_E2E_SHPOIB", "").strip() == "1"
        max_binding_attempts = 8 if shpoib_parallel else 5
        for attempt in range(max_binding_attempts):
            self.evaluate(page, f"(() => {{{source} return true; }})()")
            self.navigate(page, url, timeout_ms=timeout_ms)
            if bootstrap_js is not None:
                observed = self.evaluate(
                    page, bootstrap_js, timeout_sec=bootstrap_timeout_sec
                )
            else:
                observed = self.evaluate(
                    page,
                    """(async () => {
              const ready = window.__MYRM_E2E_RUNTIME_READY__;
              if (!ready) return {ok: false, error: 'runtime-bootstrap-missing'};
              try {
                const value = await ready;
                return {ok: true, runtimeId: value.runtimeId, apiBase: value.apiBase};
              } catch (error) {
                return {ok: false, error: String(error)};
              }
            })()""",
                    timeout_sec=bootstrap_timeout_sec,
                )
            last_observed = (
                observed if isinstance(observed, dict) else {"value": observed}
            )
            if isinstance(observed, dict) and observed.get("ok") is True:
                if (
                    observed.get("runtimeId") != expected["runtimeId"]
                    or observed.get("apiBase") != expected["apiBase"]
                ):
                    raise RuntimeError(
                        "E2E_RUNTIME_MISMATCH: "
                        f"expected={expected['runtimeId']}@{expected['apiBase']} observed={observed}"
                    )
                return
            error_text = (
                str(last_observed.get("error", last_observed))
                if isinstance(last_observed, dict)
                else str(last_observed)
            )
            fetch_transient = (
                "Failed to fetch" in error_text or "fetch" in error_text.lower()
            )
            page_transient = (
                "Target closed" in error_text or "No page found" in error_text
            )
            if attempt + 1 < max_binding_attempts and page_transient:
                time.sleep(4.0 * (attempt + 1))
                continue
            if attempt + 1 < max_binding_attempts and fetch_transient and api_base:
                wait_e2e_provider_ready(
                    api_url=api_base, timeout_sec=bootstrap_timeout_sec
                )
                time.sleep(4.0 * (attempt + 1))
                self.navigate(page, "about:blank", timeout_ms=min(timeout_ms, 30_000))
                continue
            break
        raise RuntimeError(f"E2E_RUNTIME_BINDING_FAILED: {last_observed}")

    def new_page(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        isolated_context: str | None = None,
    ) -> McpPage:
        if self._use_daemon:
            return self._daemon_new_page(url)
        from mux.transport_supervisor import assert_mux_daemons_single

        assert_mux_daemons_single(phase="new_page")
        resolved_timeout_ms = (
            timeout_ms if timeout_ms is not None else self._default_page_timeout_ms()
        )
        if self._tool_wall_deadline is None:
            resolved_timeout_ms = _parallel_scaled_page_timeout_ms(resolved_timeout_ms)
        elif timeout_ms is not None:
            remaining_sec = self._tool_wall_deadline - time.monotonic()
            if remaining_sec > 0:
                resolved_timeout_ms = min(
                    resolved_timeout_ms, max(5_000, int(remaining_sec * 1000))
                )
        context_id = (
            isolated_context.strip()
            if isolated_context is not None
            else self._browser_context_id
        )
        if isolated_context is not None and not context_id:
            raise ValueError("isolated_context must not be empty")
        if isolated_context is not None:
            from e2e_core.auth_provisioner import (  # noqa: PLC0415
                assert_auth_template_ready_for_isolated_context,
                hydrate_auth_template_for_context,
            )

            assert_auth_template_ready_for_isolated_context()
            hydrate_auth_template_for_context(context_id=context_id)
        lease_id = self._acquire_page_lease()
        page: McpPage | None = None
        runtime_binding = self._runtime_binding_source_for(url)
        _ensure_cdp_ready_before_parallel_new_page(self)
        with browser_operation_credit_slot():
            try:
                self._heartbeat_lease(lease_id)
                # Slot acquisition serializes mux admission; no stagger while holding credit.
                initial_url = "about:blank" if runtime_binding is not None else url
                arguments: dict[str, object] = {
                    "url": initial_url,
                    "timeout": resolved_timeout_ms,
                    "background": True,
                }
                if isolated_context is not None:
                    arguments["isolatedContext"] = context_id
                page_id: int
                target_id: str
                new_page_result: dict[str, object] | None = None
                parse_attempts = _new_page_retry_attempts()
                if self._open_page_budget_active():
                    parse_attempts = _new_page_tool_max_attempts(
                        open_page_budget_active=True
                    )
                mux_attach_restarted = False
                last_parsed_target_id = ""
                for parse_attempt in range(parse_attempts):
                    if parse_attempt > 0 and last_parsed_target_id:
                        self._abort_unpublished_targets()
                        last_parsed_target_id = ""
                    self._check_tool_wall_deadline("new_page")
                    try:
                        new_page_result = self.call_tool(
                            "new_page",
                            arguments,
                            timeout_sec=self._page_tool_timeout_sec(
                                resolved_timeout_ms
                            ),
                        )
                        page_id, target_id = parse_new_page(new_page_result)
                        last_parsed_target_id = target_id
                        self._track_unpublished_target(target_id)
                        break
                    except (RuntimeError, TimeoutError) as exc:
                        if not _is_retryable_new_page_parse_exc(exc, new_page_result):
                            raise
                        if parse_attempt + 1 >= parse_attempts:
                            raise
                        self._check_tool_wall_deadline("new_page_recover")
                        if not mux_attach_restarted and parse_attempt + 1 >= max(
                            2, parse_attempts // 2
                        ):
                            try:
                                from mux.transport_supervisor import (
                                    should_defer_cold_shim_restart,
                                )

                                if not should_defer_cold_shim_restart():
                                    from mux.attach_force_restart import (
                                        force_mux_attach_restart_scoped,
                                    )

                                    force_mux_attach_restart_scoped(
                                        reason="new_page timeout under parallel mux load"
                                    )
                                    mux_attach_restarted = True
                            except ImportError:
                                pass
                        if isinstance(
                            exc, RuntimeError
                        ) and _is_new_page_cdp_drift_message(str(exc)):
                            _recover_new_page_chrome_drift(self)
                        else:
                            self._recover_mux_transport()
                        time.sleep(
                            _tool_retry_backoff_sec(
                                "new_page", parse_attempt, transient=True
                            )
                            + min(2.0, 0.25 * _parallel_mux_peer_count())
                        )
                        self._heartbeat_lease(lease_id)
                else:
                    raise RuntimeError("Chrome MCP new_page failed without response")
                page = McpPage(
                    page_id=page_id,
                    target_id=target_id,
                    lease_id=lease_id,
                    context_id=context_id,
                    url=url,
                )
                self._heartbeat_lease(lease_id)
                try:
                    self._bind_page_lease(page)
                except RuntimeError as exc:
                    if "LEASE_NOT_ACTIVE" not in str(exc):
                        raise
                    lease_id = self._acquire_page_lease()
                    page = McpPage(
                        page_id=page_id,
                        target_id=target_id,
                        lease_id=lease_id,
                        context_id=context_id,
                        url=url,
                    )
                    self._heartbeat_lease(lease_id)
                    self._bind_page_lease(page)
                self._pages[page_id] = page
                self._disconnected_pages.pop(page_id, None)
                if not self._atomic_register_page(page_id):
                    self._pages.pop(page_id, None)
                    try:
                        self.call_tool(
                            "close_page",
                            {"pageId": page_id},
                            timeout_sec=_CLEANUP_TIMEOUT_SEC,
                        )
                    except (RuntimeError, TimeoutError):
                        _http_close_exact_target(page.target_id)
                    self._commit_unpublished_target(page.target_id)
                    self._release_lease(lease_id, close_wave_if_idle=False)
                    raise RuntimeError(
                        "E2E_OWNERSHIP_REGISTER_FAILED: "
                        f"page={page_id} target={page.target_id} "
                        "compensating deletion executed"
                    )
                self._commit_unpublished_target(page.target_id)
                self._cold_shim_recover_streak = 0
                self._page_lease_heartbeat.track(lease_id)
                if runtime_binding is not None:
                    self._bind_and_navigate_runtime_page(
                        page,
                        url,
                        runtime_binding,
                        timeout_ms=resolved_timeout_ms,
                    )
                return page
            except Exception as exc:
                cleanup_errors: list[str] = []
                keep_target = (
                    frozenset({page.target_id.strip()})
                    if page is not None
                    else frozenset()
                )
                if page is not None:
                    try:
                        self.call_tool(
                            "close_page",
                            {"pageId": page.page_id},
                            timeout_sec=_CLEANUP_TIMEOUT_SEC,
                        )
                    except (RuntimeError, TimeoutError) as cleanup_exc:
                        cleanup_errors.append(f"close_page: {cleanup_exc}")
                        if page.target_id.strip() and not _http_close_exact_target(
                            page.target_id
                        ):
                            cleanup_errors.append(
                                f"http_close: targetId={page.target_id.strip()} failed"
                            )
                        elif page.target_id.strip():
                            cleanup_errors[:] = [
                                item
                                for item in cleanup_errors
                                if not item.startswith("close_page:")
                            ]
                    self._commit_unpublished_target(page.target_id)
                self._abort_unpublished_targets(keep=keep_target)
                try:
                    self._release_lease(lease_id, close_wave_if_idle=False)
                except (RuntimeError, TimeoutError) as cleanup_exc:
                    cleanup_errors.append(f"release lease: {cleanup_exc}")
                if cleanup_errors:
                    raise RuntimeError(
                        f"Chrome MCP new_page failed: {exc}; cleanup failed: "
                        + "; ".join(cleanup_errors)
                    ) from exc
                raise

    def close_page(self, page: McpPage, *, ignore_errors: bool = False) -> None:
        if self._use_daemon:
            self._daemon_close_page(page, ignore_errors=ignore_errors)
            return
        errors: list[str] = []
        self._page_lease_heartbeat.untrack(page.lease_id)
        mcp_closed = False
        try:
            self.call_tool(
                "close_page",
                {"pageId": page.page_id},
                timeout_sec=_CLEANUP_TIMEOUT_SEC,
            )
            mcp_closed = True
        except (RuntimeError, TimeoutError) as exc:
            if is_context_reset_error(exc):
                _LOGGER.warning(
                    "close_page skipped after mux context reset; using HTTP close fallback"
                )
            else:
                errors.append(f"close_page: {exc}")
        if not mcp_closed and page.target_id.strip():
            if _http_close_exact_target(page.target_id):
                errors = [item for item in errors if not item.startswith("close_page:")]
            else:
                errors.append(f"http_close: targetId={page.target_id.strip()} failed")
        physically_closed = mcp_closed or not errors
        if physically_closed:
            self._pages.pop(page.page_id, None)
            self._disconnected_pages.pop(page.page_id, None)
            self._publish_dev_gate_ownership()
        try:
            self._release_page_lease(page, unbind=physically_closed)
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"release lease: {exc}")
        if not errors:
            return
        message = "Chrome MCP page cleanup failed: " + "; ".join(errors)
        if ignore_errors or all(_is_benign_cleanup_error(part) for part in errors):
            if not physically_closed:
                self._pages.pop(page.page_id, None)
                self._disconnected_pages.pop(page.page_id, None)
            _LOGGER.warning(message)
            return
        raise RuntimeError(message)

    def _publish_dev_gate_ownership(self) -> None:
        """Sync full browser ownership snapshot to coordinator (non-atomic fallback)."""
        session_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
        owner_token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
        if not session_id or not owner_token:
            return
        try:
            from dev_gate.cli import send

            send(
                {
                    "operation": "ownership",
                    "session_id": session_id,
                    "owner_token": owner_token,
                    "ownership": {
                        "browser_context_id": self._browser_context_id,
                        "page_ids": [str(page_id) for page_id in sorted(self._pages)],
                        "lease_id": self._parent_lease_id,
                        "runtime_id": os.environ.get("MYRM_E2E_RUNTIME_ID", "").strip(),
                    },
                }
            )
        except (ImportError, OSError, RuntimeError, ValueError) as exc:
            _LOGGER.warning("DEV_GATE_OWNERSHIP_PUBLISH_WARN: %s", exc)

    def _atomic_register_page(self, page_id: int) -> bool:
        """Atomically register a new page via CAS; returns False on conflict/failure."""
        session_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
        owner_token = os.environ.get("MYRM_E2E_RUNTIME_OWNER_TOKEN", "").strip()
        if not session_id or not owner_token:
            return True
        try:
            from dev_gate.cli import send
        except ImportError as exc:
            _LOGGER.warning("DEV_GATE_ATOMIC_REGISTER_FAILED: %s", exc)
            return False

        max_attempts = 5
        for attempt in range(max_attempts):
            try:
                snapshot = send({"operation": "snapshot", "session_id": session_id})
                session = snapshot.get("session")
                version = session.get("version") if isinstance(session, dict) else None
                if not isinstance(version, int):
                    self._publish_dev_gate_ownership()
                    return True
                send(
                    {
                        "operation": "ownership",
                        "session_id": session_id,
                        "owner_token": owner_token,
                        "merge_page_id": str(page_id),
                        "expected_version": version,
                    }
                )
                return True
            except (OSError, RuntimeError, ValueError) as exc:
                message = str(exc).lower()
                retryable = (
                    "version mismatch" in message
                    or "version conflict" in message
                    or "empty coordinator response" in message
                    or "dev_gate_coordinator_error" in message
                    or "timeout" in message
                    or "timed out" in message
                    or "locked" in message
                )
                if retryable and attempt + 1 < max_attempts:
                    time.sleep(0.06 * float(attempt + 1))
                    continue
                try:
                    from dev_gate.cli import send as _dev_gate_send

                    _dev_gate_send(
                        {
                            "operation": "ownership",
                            "session_id": session_id,
                            "owner_token": owner_token,
                            "ownership": {
                                "browser_context_id": self._browser_context_id,
                                "page_ids": [str(pid) for pid in sorted(self._pages)],
                                "lease_id": self._parent_lease_id,
                                "runtime_id": os.environ.get(
                                    "MYRM_E2E_RUNTIME_ID", ""
                                ).strip(),
                            },
                        }
                    )
                    return True
                except (OSError, RuntimeError, ValueError) as fallback_exc:
                    _LOGGER.warning(
                        "DEV_GATE_ATOMIC_REGISTER_FAILED: %s; fallback=%s",
                        exc,
                        fallback_exc,
                    )
                    return False
        return False

    def _resolve_page(self, page: McpPage) -> McpPage:
        tracked = self._pages.get(page.page_id)
        if tracked is not None:
            return tracked
        for pages in (self._pages, self._disconnected_pages):
            for candidate in pages.values():
                if candidate.lease_id == page.lease_id:
                    return candidate
        return page

    def _ensure_page_tracked_for_recovery(self, page: McpPage) -> None:
        """Expose orphan McpPage handles to mux recovery instead of cold shim (R115)."""
        if page.page_id in self._pages or page.page_id in self._disconnected_pages:
            return
        self._disconnected_pages[page.page_id] = page

    def _lookup_page_for_reclaim(self, page_id: int) -> McpPage | None:
        page = self._pages.get(page_id)
        if page is not None:
            return page
        page = self._disconnected_pages.get(page_id)
        if page is not None:
            return page
        for pool in (self._pages, self._disconnected_pages):
            for candidate in pool.values():
                if candidate.page_id == page_id:
                    return candidate
        if len(self._pages) == 1:
            return next(iter(self._pages.values()))
        if len(self._disconnected_pages) == 1:
            return next(iter(self._disconnected_pages.values()))
        return None

    @staticmethod
    def _collapse_pages_for_recovery(
        saved_pages: dict[int, McpPage],
    ) -> dict[int, McpPage]:
        """Keep one page for mux recovery — parallel orphan cycles accumulate stale ids."""
        if len(saved_pages) <= 1:
            return saved_pages
        by_lease: dict[str, McpPage] = {}
        for page in saved_pages.values():
            lease_key = page.lease_id.strip() or f"page-{page.page_id}"
            current = by_lease.get(lease_key)
            if current is None or page.page_id > current.page_id:
                by_lease[lease_key] = page
        if len(by_lease) == 1:
            only = next(iter(by_lease.values()))
            return {only.page_id: only}
        newest = max(by_lease.values(), key=lambda candidate: candidate.page_id)
        return {newest.page_id: newest}

    def primary_owned_page(self) -> McpPage | None:
        if not self._pages:
            return None
        return max(self._pages.values(), key=lambda page: page.page_id)

    def ensure_primary_page_after_recovery(
        self,
        *,
        fallback_url: str,
        timeout_ms: int = 120_000,
    ) -> McpPage:
        existing = self.primary_owned_page()
        if existing is not None:
            return existing
        fresh = self.new_page(fallback_url, timeout_ms=timeout_ms)
        if fresh is None:
            raise RuntimeError(
                "Chrome MCP ensure_primary_page_after_recovery: new_page returned None"
            )
        return fresh

    def _maybe_refresh_tool_page_arguments(
        self, arguments: dict[str, object]
    ) -> dict[str, object]:
        if "pageId" not in arguments:
            return arguments
        primary = self.primary_owned_page()
        if primary is None:
            return arguments
        refreshed = dict(arguments)
        refreshed["pageId"] = primary.page_id
        return refreshed

    def _heal_after_context_reset(self) -> None:
        """R96-MUX: rebuild owned pages via new_page after mux context reset."""
        from mux.transport_recovery_core import TransportRecoveryMode

        saved_pages = self._collapse_pages_for_recovery(
            {**self._disconnected_pages, **self._pages}
        )
        if not saved_pages:
            return
        _LOGGER.warning(
            "R96_MUX_CONTEXT_RESET_HEAL: rebuilding %d owned page(s) via new_page",
            len(saved_pages),
        )
        self._pages.clear()
        for page in saved_pages.values():
            self._disconnected_pages[page.page_id] = page
        reclaim_deadline = _reclaim_wall_deadline()
        trsm_mode = self._resolve_trsm_mode()
        if trsm_mode == TransportRecoveryMode.PARALLEL_PAGE_RECLAIM:
            self._reclaim_pages_parallel_safe(saved_pages, reclaim_deadline)
        if not self._pages:
            self._rebuild_disconnected_pages(saved_pages, reclaim_deadline)
        try:
            from e2e_core.runtime_cell import bump_cell_mux_generation, current_cell_id

            if current_cell_id():
                bump_cell_mux_generation()
        except ImportError:
            pass

    def reclaim_owned_page(self, page: McpPage) -> McpPage:
        """Reopen one mux-owned page after ownership loss and return the live page."""
        resolved = self._lookup_page_for_reclaim(page.page_id) or page
        reopened = self._reopen_owned_page(resolved)
        self._disconnected_pages.pop(resolved.page_id, None)
        return reopened

    def _resolve_evaluate_timeout_sec(self, timeout_sec: float) -> float:
        if timeout_sec <= _EXPLICIT_SHORT_TOOL_TIMEOUT_CEILING_SEC:
            return timeout_sec
        return self._resolve_tool_timeout_sec(
            max(timeout_sec, _LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC)
        )

    def evaluate(
        self,
        page: McpPage,
        expression: str,
        *,
        timeout_sec: float = 15.0,
        await_promise: bool = True,
    ) -> object:
        if self._use_daemon:
            return self._daemon_evaluate(
                page,
                expression,
                timeout_sec=timeout_sec,
                await_promise=await_promise,
            )
        resolved = self._resolve_page(page)
        self._ensure_page_tracked_for_recovery(resolved)
        function = f"async () => await (0, eval)({json.dumps(expression)})"
        effective_timeout = self._resolve_evaluate_timeout_sec(timeout_sec)
        probe_mode = timeout_sec <= _EXPLICIT_SHORT_TOOL_TIMEOUT_CEILING_SEC
        for reload_attempt in range(3):
            try:
                result = self.call_tool(
                    "evaluate_script",
                    {"pageId": resolved.page_id, "function": function},
                    timeout_sec=effective_timeout,
                    is_probe=probe_mode,
                )
                return parse_evaluate_result(result)
            except RuntimeError as exc:
                message = str(exc)
                if reload_attempt < 2 and _is_page_ownership_error(message):
                    if getattr(self, "_reclaim_in_progress", False):
                        time.sleep(0.3)
                        resolved = self._resolve_page(page)
                        continue
                    resolved = self.reclaim_owned_page(resolved)
                    continue
                if reload_attempt == 0 and (
                    "Execution context was destroyed" in message
                    or "detached Frame" in message
                ):
                    target_url = (resolved.url or "http://127.0.0.1:3000").strip()
                    self.navigate(resolved, target_url, timeout_ms=60_000)
                    resolved = self._resolve_page(page)
                    continue
                if reload_attempt < 2 and (
                    "Target closed" in message or "No page found" in message
                ):
                    resolved = self.reclaim_owned_page(resolved)
                    continue
                raise
        raise RuntimeError("Chrome MCP evaluate exhausted reload attempts")

    def navigate(
        self,
        page: McpPage,
        url: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        if self._use_daemon:
            self._daemon_navigate(page, url)
            return
        resolved = self._resolve_page(page)
        resolved_timeout_ms = (
            timeout_ms if timeout_ms is not None else self._default_page_timeout_ms()
        )

        def _navigate_resolved(target: McpPage) -> None:
            self.call_tool(
                "navigate_page",
                {
                    "pageId": target.page_id,
                    "type": "url",
                    "url": url,
                    "timeout": resolved_timeout_ms,
                },
                timeout_sec=self._page_tool_timeout_sec(resolved_timeout_ms),
            )

        for ownership_attempt in range(3):
            try:
                _navigate_resolved(resolved)
                return
            except RuntimeError as exc:
                if _is_page_ownership_error(str(exc)):
                    if getattr(self, "_reclaim_in_progress", False):
                        time.sleep(0.3)
                        resolved = self._resolve_page(page)
                        continue
                    if ownership_attempt >= 2:
                        raise
                    resolved = self.reclaim_owned_page(resolved)
                    continue
                if "timeout" not in str(exc).lower():
                    raise
                probe = self.evaluate(
                    resolved,
                    "({href: location.href, bodyLength: document.body?.innerText?.length ?? 0})",
                    timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
                )
                if not isinstance(probe, dict):
                    raise exc
                href = probe.get("href")
                body_length = probe.get("bodyLength")
                if href != url or not isinstance(body_length, int) or body_length <= 0:
                    raise exc
                return
            except TimeoutError as exc:
                probe = self.evaluate(
                    resolved,
                    "({href: location.href, bodyLength: document.body?.innerText?.length ?? 0})",
                    timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
                )
                if not isinstance(probe, dict):
                    raise exc
                href = probe.get("href")
                body_length = probe.get("bodyLength")
                if href != url or not isinstance(body_length, int) or body_length <= 0:
                    raise exc
                return
        raise RuntimeError(
            f"{MUX_RECLAIM_STALL_TOKEN}: navigate exhausted ownership retries"
        )

    def reload(self, page: McpPage, *, timeout_ms: int = 15_000) -> None:
        resolved = self._resolve_page(page)
        if self._use_daemon:
            client = self._ensure_daemon_session()
            session_id = self._daemon_session_id
            assert session_id is not None
            client.evaluate_page(
                session_id,
                resolved.target_id,
                "window.location.reload(); true",
                timeout_sec=min(timeout_ms / 1000 + 5, self._request_timeout_sec),
            )
            return
        self.call_tool(
            "navigate_page",
            {"pageId": resolved.page_id, "type": "reload", "timeout": timeout_ms},
            timeout_sec=min(timeout_ms / 1000 + 5, self._request_timeout_sec),
        )

    def press_key(self, page: McpPage, key: str) -> None:
        resolved = self._resolve_page(page)
        if self._use_daemon:
            client = self._ensure_daemon_session()
            session_id = self._daemon_session_id
            assert session_id is not None
            key_literal = json.dumps(key)
            client.evaluate_page(
                session_id,
                resolved.target_id,
                f"""(() => {{
                  const el = document.activeElement ?? document.body;
                  el.dispatchEvent(new KeyboardEvent('keydown', {{ key: {key_literal}, bubbles: true }}));
                  el.dispatchEvent(new KeyboardEvent('keyup', {{ key: {key_literal}, bubbles: true }}));
                  return {{ ok: true }};
                }})()""",
                timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
            )
            return
        self.call_tool(
            "press_key",
            {"pageId": resolved.page_id, "key": key},
            timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
        )

    def type_text(self, page: McpPage, text: str) -> None:
        resolved = self._resolve_page(page)
        if self._use_daemon:
            client = self._ensure_daemon_session()
            session_id = self._daemon_session_id
            assert session_id is not None
            escaped = json.dumps(text)
            client.evaluate_page(
                session_id,
                resolved.target_id,
                f"""(() => {{
                  const el = document.activeElement;
                  if (!el) throw new Error('no active element for type_text');
                  if ('value' in el) {{
                    el.value = {escaped};
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return {{ ok: true }};
                  }}
                  throw new Error('active element is not typeable');
                }})()""",
                timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
            )
            return
        self.call_tool(
            "type_text",
            {"pageId": resolved.page_id, "text": text},
            timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
        )

    def _ensure_shim_transport(self) -> None:
        process = self._process
        if process is None:
            return
        if process.poll() is None:
            return
        self._recover_mux_transport()

    def _reopen_owned_page(self, page: McpPage) -> McpPage:
        depth = getattr(self, "_reclaim_depth", 0)
        if depth >= 1:
            from dev_gate.contract import MUX_RECLAIM_STALL_TOKEN

            wait_deadline = time.monotonic() + min(
                30.0,
                max(1.0, _remaining_reclaim_sec(_reclaim_wall_deadline())),
            )
            lookup_id = page.page_id
            while time.monotonic() < wait_deadline:
                if getattr(self, "_reclaim_depth", 0) < 1:
                    tracked = self._lookup_page_for_reclaim(lookup_id)
                    if tracked is not None and tracked.page_id in self._pages:
                        return self._resolve_page(tracked)
                    break
                time.sleep(0.2)
            raise RuntimeError(
                f"{MUX_RECLAIM_STALL_TOKEN}: nested page reclaim during active recovery"
            )
        self._reclaim_in_progress = True
        self._reclaim_depth = depth + 1
        try:
            return self._reopen_owned_page_inner(page)
        finally:
            self._reclaim_depth = depth
            if depth == 0:
                self._reclaim_in_progress = False

    def _reopen_owned_page_inner(self, page: McpPage) -> McpPage:
        if self._use_daemon:
            from dev_gate.contract import E2E_USER_CLOSED_TAB_TOKEN

            raise RuntimeError(
                f"{E2E_USER_CLOSED_TAB_TOKEN}: orchestrator path does not reopen tabs "
                "(external close or transport loss is terminal)"
            )
        from chrome_e2e.gates.diagnostic_policy import assert_mux_diagnostic_only

        assert_mux_diagnostic_only(operation="page reopen")
        from chrome_e2e.mux.diagnostic_recovery import reopen_owned_page_inner

        return reopen_owned_page_inner(self, page)

    def _call_tool_direct(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        response = self._request(
            "tools/call",
            {"name": name, "arguments": arguments},
            timeout_sec=timeout_sec,
        )
        result = response.get("result")
        if not isinstance(result, dict):
            raise RuntimeError(f"Chrome MCP {name} returned invalid result: {response}")
        if result.get("isError") is True:
            raise RuntimeError(f"Chrome MCP {name} failed: {text_content(result)}")
        return result

    def _maybe_reclaim_page_arguments(
        self,
        arguments: dict[str, object],
        *,
        error_message: str,
    ) -> dict[str, object] | None:
        if not _is_page_ownership_error(error_message):
            return None
        self._ensure_shim_transport()
        raw_page_id = arguments.get("pageId")
        if not isinstance(raw_page_id, int):
            return None
        page = self._lookup_page_for_reclaim(raw_page_id)
        if page is None:
            return None
        reopened = self._reopen_owned_page(page)
        self._disconnected_pages.pop(page.page_id, None)
        updated = dict(arguments)
        updated["pageId"] = reopened.page_id
        return updated

    def _teardown_shim_process(self) -> None:
        import traceback as _tb

        process = self._process
        self._process = None
        if self._pages:
            self._disconnected_pages.update(self._pages)
        self._pages.clear()
        if process is None:
            return
        pid = process.pid
        rc = process.poll()
        caller = "".join(_tb.format_stack()[-4:-1])
        _LOGGER.warning(
            "SHIM_TEARDOWN: pid=%s rc=%s pages_saved=%d caller:\n%s",
            pid,
            rc,
            len(self._disconnected_pages),
            caller,
        )
        try:
            if process.stdin is not None:
                process.stdin.close()
            process.terminate()
            process.wait(timeout=3)
        except Exception as exc:
            _LOGGER.warning("Chrome MCP transport teardown warning: %s", exc)

    def _spawn_shim_process(self) -> None:
        if shutil.which("node") is None:
            raise RuntimeError("Chrome MCP runner requires node")
        shim = self._monorepo_root / "scripts/dev/cdmcp-mux-autoconnect-shim.sh"
        if not shim.is_file():
            raise RuntimeError(f"Chrome MCP shim missing: {shim}")
        self._process = subprocess.Popen(
            ["bash", str(shim)],
            cwd=str(self._monorepo_root),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env={
                **os.environ,
                "CDMCP_MUX_REQUEST_TIMEOUT_MS": os.environ.get(
                    "CDMCP_MUX_REQUEST_TIMEOUT_MS", "180000"
                ),
            },
        )
        assert self._process.stderr is not None
        self._stderr_thread = threading.Thread(
            target=self._drain_stderr,
            args=(self._process.stderr,),
            name="chrome-mcp-stderr",
            daemon=True,
        )
        self._stderr_thread.start()

    def _initialize_shim_session(self) -> None:
        held_lock = self._acquire_request_lock()
        saved_tool_wall = self._tool_wall_deadline
        self._tool_wall_deadline = None
        try:
            process = self._require_live_process()
            response = self._exchange_locked(
                process,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "myrm-pytest-mcp",
                        "version": "1.0",
                        "sessionId": self._browser_context_id,
                    },
                },
                timeout_sec=self._resolve_tool_timeout_sec(None),
            )
            result = response.get("result")
            if not isinstance(result, dict) or not isinstance(
                result.get("capabilities"), dict
            ):
                self._teardown_shim_process()
                raise RuntimeError(
                    f"Chrome MCP initialize returned invalid result: {response}"
                )
            process = self._require_live_process()
            self._write(
                process,
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                    "params": {},
                },
            )
        finally:
            self._tool_wall_deadline = saved_tool_wall
            self._release_request_lock(held_lock)
        self._page_lease_heartbeat.start()

    def _restart_cold_shim(self) -> None:
        """Restart local MCP shim when this client owns no pages (R109).

        Per-session shim teardown/spawn is local; global mux attach restart runs under
        ``mux_recovery_scope`` so parallel workers never stampede daemon restart.
        """
        from mux.transport_supervisor import (
            mux_recovery_scope,
            parallel_mux_peer_count,
            should_defer_cold_shim_restart,
        )

        def _respawn_cold_shim_local() -> None:
            held_inner = self._acquire_request_lock()
            try:
                self._teardown_shim_process()
                last_error: RuntimeError | None = None
                for attempt in range(_TRANSPORT_RECOVER_ATTEMPTS):
                    try:
                        self._spawn_shim_process()
                        self._initialize_shim_session()
                        return
                    except RuntimeError as exc:
                        last_error = exc
                        self._teardown_shim_process()
                        if attempt + 1 < _TRANSPORT_RECOVER_ATTEMPTS:
                            time.sleep(min(0.75 * (attempt + 1), 2.0))
                if last_error is not None:
                    raise last_error
                raise RuntimeError("Chrome MCP cold shim restart failed")
            finally:
                self._release_request_lock(held_inner)

        if should_defer_cold_shim_restart():
            peer_count = parallel_mux_peer_count()
            _LOGGER.warning(
                "COLD_SHIM_RESTART_DEFERRED: parallel_mux_peers=%d — queue for "
                "mux recovery lock then respawn (do not stop other pytest)",
                peer_count,
            )
            with mux_recovery_scope(phase="restart_cold_shim_deferred"):
                _respawn_cold_shim_local()
            return

        needs_global_restart = False
        held_lock = self._acquire_request_lock()
        try:
            _LOGGER.warning(
                "RECOVER_MUX_COLD_SHIM: pages=0 disconnected=%d streak=%d",
                len(self._disconnected_pages),
                self._cold_shim_recover_streak + 1,
            )
            self._cold_shim_recover_streak += 1
            if self._cold_shim_recover_streak >= 2:
                needs_global_restart = True
                self._cold_shim_recover_streak = 0
        finally:
            self._release_request_lock(held_lock)

        if needs_global_restart:
            from mux.attach_force_restart import force_mux_attach_restart_deduped

            with mux_recovery_scope(phase="restart_cold_shim"):
                if force_mux_attach_restart_deduped(
                    reason="cold shim recover streak (new_page)"
                ):
                    time.sleep(3.0)
                _respawn_cold_shim_local()
            return
        if parallel_mux_peer_count() >= 2:
            with mux_recovery_scope(phase="restart_cold_shim"):
                _respawn_cold_shim_local()
            return
        _respawn_cold_shim_local()

    def _recover_mux_transport(self, *, start_generation: int | None = None) -> None:
        from chrome_e2e.gates.diagnostic_policy import assert_mux_diagnostic_only

        if self._use_daemon:
            return
        assert_mux_diagnostic_only(operation="transport recovery")
        try:
            from chrome_e2e.gates.orphan_budget import (
                assert_orphan_budget_invariant,
            )  # noqa: PLC0415

            assert_orphan_budget_invariant()
        except ImportError:
            pass
        if not self._pages and not self._disconnected_pages:
            self._restart_cold_shim()
            return
        from mux.transport_supervisor import mux_recovery_scope

        with mux_recovery_scope(phase="recover_mux_transport"):
            self._recover_mux_transport_inner(start_generation=start_generation)

    def _recover_mux_transport_inner(
        self, *, start_generation: int | None = None
    ) -> None:
        from chrome_e2e.gates.diagnostic_policy import assert_mux_diagnostic_only

        assert_mux_diagnostic_only(operation="transport recovery inner")
        from chrome_e2e.mux.diagnostic_recovery import recover_mux_transport_inner

        recover_mux_transport_inner(self, start_generation=start_generation)

    def _rebuild_disconnected_pages(
        self,
        saved_pages: dict[int, McpPage],
        reclaim_deadline: float,
    ) -> None:
        """Best-effort rebuild of pages after transport recovery (shim restart).

        The new shim has an empty ``ownedPageIds``; old browser tabs may still exist
        but the daemon cleaned up their context ownership.  We open fresh tabs at
        the same URLs, bind them to existing leases, and update ``_pages`` so that
        callers transparently get a live page.

        If runtime binding verification fails (e.g. new page routed to wrong
        parallel test runtime), the page is immediately closed and the old page
        remains in ``_disconnected_pages`` so callers get a clear error.
        """
        from chrome_e2e.gates.diagnostic_policy import assert_mux_diagnostic_only

        assert_mux_diagnostic_only(operation="page rebuild")
        from chrome_e2e.mux.diagnostic_recovery import rebuild_disconnected_pages

        rebuild_disconnected_pages(self, saved_pages, reclaim_deadline)

    def _reclaim_pages_parallel_safe(
        self,
        saved_pages: dict[int, McpPage],
        reclaim_deadline: float,
    ) -> None:
        """R69-C: page-level reclaim when global shim teardown would harm peer sessions."""
        if not saved_pages:
            return
        if getattr(self, "_reclaim_in_progress", False):
            _LOGGER.warning(
                "RECOVER_MUX_PARALLEL_RECLAIM: skip nested reclaim during active recovery"
            )
            return
        peer_count = _parallel_mux_peer_count()
        for old_page_id, old_page in saved_pages.items():
            remaining = _remaining_reclaim_sec(reclaim_deadline)
            if remaining < 5.0:
                _LOGGER.warning(
                    "RECOVER_MUX_PARALLEL_RECLAIM: budget exhausted; page %d skipped",
                    old_page_id,
                )
                break
            try:
                reclaimed = self.reclaim_owned_page(old_page)
                self._pages[reclaimed.page_id] = reclaimed
                self._disconnected_pages.pop(old_page_id, None)
                _LOGGER.info(
                    "RECOVER_MUX_PARALLEL_RECLAIM: page %d→%d peers=%d",
                    old_page_id,
                    reclaimed.page_id,
                    peer_count,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "RECOVER_MUX_PARALLEL_RECLAIM: page %d failed: %s",
                    old_page_id,
                    exc,
                )
                try:
                    self._rebuild_disconnected_pages(
                        {old_page_id: old_page},
                        reclaim_deadline,
                    )
                except Exception as rebuild_exc:
                    _LOGGER.warning(
                        "RECOVER_MUX_PARALLEL_REBUILD: page %d failed: %s",
                        old_page_id,
                        rebuild_exc,
                    )

    def abandon_inflight_requests(self, *, cdp_drift: bool = False) -> None:
        """Invalidate orphaned mux I/O after asyncio cancelled a blocking evaluate thread."""
        self._abort_unpublished_targets()
        _LOGGER.warning(
            "ABANDON_INFLIGHT: gen=%d→%d",
            self._request_generation,
            self._request_generation + 1,
        )
        self._request_generation += 1
        try:
            from e2e_core.runtime_cell import current_cell_id, persist_cell_mux_generation

            if current_cell_id():
                persist_cell_mux_generation(self._request_generation)
        except ImportError:
            pass
        self._page_lease_heartbeat.stop()
        self._reclaim_in_progress = False
        from mux.transport_recovery_core import TRSM_MODE_TOKEN, should_skip_global_teardown

        trsm_mode = self._resolve_trsm_mode()
        if should_skip_global_teardown(trsm_mode) and not cdp_drift:
            _LOGGER.warning(
                "ABANDON_INFLIGHT_SKIPPED_TEARDOWN: %s=%s parallel_mux_peers=%d",
                TRSM_MODE_TOKEN,
                trsm_mode.value,
                _parallel_mux_peer_count(),
            )
        elif should_skip_global_teardown(trsm_mode) and cdp_drift:
            _LOGGER.warning(
                "ABANDON_INFLIGHT_SCOPED_HEAL: %s=%s cdp_drift parallel_mux_peers=%d",
                TRSM_MODE_TOKEN,
                trsm_mode.value,
                _parallel_mux_peer_count(),
            )
            _recover_new_page_chrome_drift(self)
        else:
            self._teardown_shim_process()
        # Orphan to_thread may still hold the old lock in select(); replace so recover
        # on the event loop thread cannot deadlock (R49-R50).
        self._request_lock = _TrackedRLock()

    def reset_after_orphan(self) -> None:
        """Single orphan recovery entry: invalidate in-flight mux I/O and restart transport."""
        try:
            from e2e_session_runtime.lifecycle import touch_wall_progress

            touch_wall_progress(current_node="reset_after_orphan")
        except ImportError:
            pass
        self.abandon_inflight_requests()
        self._recover_mux_transport()

    def recover_mux_transport(self) -> None:
        """Restart MCP shim after mux timeout or transport drift (E2E orchestrator hook)."""
        if self._request_lock_is_held():
            self.reset_after_orphan()
            return
        self._recover_mux_transport()

    def call_tool(
        self,
        name: str,
        arguments: dict[str, object],
        *,
        timeout_sec: float | None = None,
        is_probe: bool = False,
    ) -> dict[str, object]:
        """Execute one MCP tool call with automatic retry and transport recovery.

        Args:
            is_probe: When True, timeout/transient failures will NOT trigger
                ``_recover_mux_transport`` (shim restart). Probes are short-lived
                status polls whose failure should not destroy page ownership for
                concurrent long-running operations.
        """
        if name != "close_page":
            self._page_lease_heartbeat.raise_if_failed()
        if timeout_sec is not None:
            effective_timeout_sec = timeout_sec
        elif name == "close_page":
            effective_timeout_sec = _CLEANUP_TIMEOUT_SEC
        else:
            effective_timeout_sec = self._resolve_tool_timeout_sec(None)
        retry_tools = {"evaluate_script", "close_page", "new_page", "navigate_page"}
        last_error: BaseException | None = None
        tool_arguments = dict(arguments)
        max_attempts = _tool_retry_attempts(name)
        if name == "new_page":
            max_attempts = _new_page_tool_max_attempts(
                open_page_budget_active=self._open_page_budget_active()
            )
        for attempt in range(max_attempts):
            self._check_tool_wall_deadline(name)
            try:
                response = self._request(
                    "tools/call",
                    {"name": name, "arguments": tool_arguments},
                    timeout_sec=effective_timeout_sec,
                )
            except (TimeoutError, RuntimeError) as exc:
                last_error = exc
                message = str(exc)
                if _is_mux_parallel_fail_fast_message(message):
                    raise
                if (
                    not is_probe
                    and is_context_reset_error(exc)
                    and attempt + 1 < max_attempts
                ):
                    self._heal_after_context_reset()
                    tool_arguments = self._maybe_refresh_tool_page_arguments(
                        tool_arguments
                    )
                    time.sleep(_tool_retry_backoff_sec(name, attempt, transient=True))
                    continue
                reclaimed = None
                if not getattr(self, "_reclaim_in_progress", False):
                    reclaimed = self._maybe_reclaim_page_arguments(
                        tool_arguments,
                        error_message=message,
                    )
                if reclaimed is not None:
                    tool_arguments = reclaimed
                    if attempt + 1 < max_attempts:
                        time.sleep(
                            _tool_retry_backoff_sec(name, attempt, transient=False)
                        )
                        continue
                if (
                    not is_probe
                    and _is_page_ownership_error(message)
                    and attempt + 1 < max_attempts
                ):
                    self._recover_mux_transport()
                    time.sleep(_tool_retry_backoff_sec(name, attempt, transient=True))
                    continue
                if not is_probe and _should_recover_mux_after_tool_error(
                    name, message, retry_tools=frozenset(retry_tools)
                ):
                    if name == "new_page" and _is_new_page_cdp_drift_message(message):
                        _recover_new_page_chrome_drift(self)
                    else:
                        self._recover_mux_transport()
                    if attempt + 1 < max_attempts:
                        time.sleep(
                            _tool_retry_backoff_sec(name, attempt, transient=True)
                        )
                        continue
                transient = isinstance(exc, RuntimeError) and _is_transient_mux_error(
                    message
                )
                stale_mux_page = name == "new_page" and _STALE_MUX_PAGE_TOKEN in message
                timed_out = isinstance(exc, TimeoutError) or (
                    isinstance(exc, RuntimeError) and "timed out" in message.lower()
                )
                if (
                    self._open_page_budget_active()
                    and name == "new_page"
                    and timed_out
                    and attempt + 1 >= max_attempts
                ):
                    raise
                if not is_probe:
                    if (
                        transient and not _is_page_ownership_error(message)
                    ) or stale_mux_page:
                        raw_page_id = tool_arguments.get("pageId")
                        if isinstance(raw_page_id, int):
                            tracked = self._lookup_page_for_reclaim(raw_page_id)
                            if tracked is not None:
                                self._ensure_page_tracked_for_recovery(tracked)
                        self._recover_mux_transport()
                    elif (
                        timed_out
                        and name in retry_tools
                        and (attempt >= 1 or name == "new_page")
                    ):
                        self._recover_mux_transport()
                can_retry = attempt + 1 < max_attempts and (
                    reclaimed is not None
                    or transient
                    or timed_out
                    or stale_mux_page
                    or (name in retry_tools and isinstance(exc, TimeoutError))
                )
                if can_retry:
                    time.sleep(
                        _tool_retry_backoff_sec(name, attempt, transient=transient)
                    )
                    continue
                raise
            result = response.get("result")
            if not isinstance(result, dict):
                raise RuntimeError(
                    f"Chrome MCP {name} returned invalid result: {response}"
                )
            if result.get("isError") is True:
                message = text_content(result)
                if (
                    not is_probe
                    and is_context_reset_error(RuntimeError(message))
                    and attempt + 1 < max_attempts
                ):
                    self._heal_after_context_reset()
                    tool_arguments = self._maybe_refresh_tool_page_arguments(
                        tool_arguments
                    )
                    time.sleep(_tool_retry_backoff_sec(name, attempt, transient=True))
                    continue
                reclaimed = None
                if not getattr(self, "_reclaim_in_progress", False):
                    reclaimed = self._maybe_reclaim_page_arguments(
                        tool_arguments,
                        error_message=message,
                    )
                if reclaimed is not None:
                    tool_arguments = reclaimed
                    if attempt + 1 < max_attempts:
                        time.sleep(
                            _tool_retry_backoff_sec(name, attempt, transient=False)
                        )
                        continue
                if _is_page_ownership_error(message) and attempt + 1 < max_attempts:
                    self._recover_mux_transport()
                    time.sleep(_tool_retry_backoff_sec(name, attempt, transient=True))
                    continue
                if not is_probe and _should_recover_mux_after_tool_error(
                    name, message, retry_tools=frozenset(retry_tools)
                ):
                    last_error = RuntimeError(f"Chrome MCP {name} failed: {message}")
                    if name == "new_page" and _is_new_page_cdp_drift_message(message):
                        _recover_new_page_chrome_drift(self)
                    else:
                        self._recover_mux_transport()
                    if attempt + 1 < max_attempts:
                        time.sleep(
                            _tool_retry_backoff_sec(name, attempt, transient=True)
                        )
                        continue
                    raise last_error
                raise RuntimeError(f"Chrome MCP {name} failed: {message}")
            return result
        if last_error is not None:
            raise last_error
        raise RuntimeError(f"Chrome MCP {name} failed without response")

    def _exchange_locked(
        self,
        process: subprocess.Popen[str],
        method: str,
        params: dict[str, object],
        *,
        timeout_sec: float | None = None,
        request_generation: int | None = None,
    ) -> dict[str, object]:
        self._request_id += 1
        request_id = self._request_id
        self._write(
            process,
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": method,
                "params": params,
            },
        )
        timeout = (
            timeout_sec
            if timeout_sec is not None
            else self._resolve_tool_timeout_sec(None)
        )
        deadline = time.monotonic() + timeout
        while True:
            if (
                self._tool_wall_deadline is not None
                and time.monotonic() >= self._tool_wall_deadline
            ):
                raise TimeoutError(f"Chrome MCP {method} wall budget exhausted")
            if (
                request_generation is not None
                and request_generation != self._request_generation
            ):
                raise RuntimeError(
                    f"{MUX_RECLAIM_STALL_TOKEN}: request abandoned during I/O"
                )
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Chrome MCP {method} response timed out")
            if process.poll() is not None:
                raise _TransportDeadError(
                    f"Chrome MCP transport exited rc={process.poll()}; "
                    f"stderr={list(self._stderr_lines)[-5:]}"
                )
            try:
                response = self._read(process, min(remaining, _MCP_READ_POLL_SEC))
            except TimeoutError:
                continue
            if response.get("id") != request_id:
                continue
            error = response.get("error")
            if isinstance(error, dict):
                raise RuntimeError(
                    f"Chrome MCP {method} error: {error.get('message', error)}"
                )
            return response

    def _request(
        self,
        method: str,
        params: dict[str, object],
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        start_generation = self._request_generation
        last_transport_error: _TransportDeadError | None = None
        max_attempts = _TRANSPORT_RECOVER_ATTEMPTS
        for transport_attempt in range(max_attempts):
            try:
                held_lock = self._acquire_request_lock()
                try:
                    if start_generation != self._request_generation:
                        raise RuntimeError(
                            f"{MUX_RECLAIM_STALL_TOKEN}: request abandoned before acquire"
                        )
                    process = self._require_live_process()
                    return self._exchange_locked(
                        process,
                        method,
                        params,
                        timeout_sec=timeout_sec,
                        request_generation=start_generation,
                    )
                finally:
                    self._release_request_lock(held_lock)
            except _TransportDeadError as exc:
                last_transport_error = exc
                _LOGGER.warning(
                    "Chrome MCP transport dead during %s (attempt %s/%s): %s",
                    method,
                    transport_attempt + 1,
                    max_attempts,
                    exc,
                )
            if transport_attempt + 1 >= max_attempts:
                break
            if start_generation != self._request_generation:
                raise RuntimeError(
                    f"{MUX_RECLAIM_STALL_TOKEN}: request generation changed "
                    f"before transport recovery "
                    f"(start={start_generation} "
                    f"current={self._request_generation})"
                )
            self._recover_mux_transport(start_generation=start_generation)
        if last_transport_error is not None:
            raise RuntimeError(
                "Chrome MCP client is not running after transport recovery; "
                f"stderr tail={list(self._stderr_lines)[-5:]}"
            ) from last_transport_error
        raise RuntimeError(f"Chrome MCP {method} failed without transport")

    def _notify(self, method: str, params: dict[str, object]) -> None:
        held_lock = self._acquire_request_lock()
        try:
            process = self._require_live_process()
            self._write(
                process,
                {"jsonrpc": "2.0", "method": method, "params": params},
            )
        finally:
            self._release_request_lock(held_lock)

    def _write(
        self, process: subprocess.Popen[str], payload: dict[str, object]
    ) -> None:
        if process.stdin is None:
            raise RuntimeError("Chrome MCP stdin is unavailable")
        line = json.dumps(payload, separators=(",", ":")) + "\n"
        try:
            process.stdin.write(line)
            process.stdin.flush()
        except (BrokenPipeError, ValueError) as exc:
            raise _TransportDeadError(
                f"Chrome MCP transport closed during write; "
                f"stderr={list(self._stderr_lines)[-5:]}"
            ) from exc

    def _read(
        self, process: subprocess.Popen[str], timeout_sec: float
    ) -> dict[str, object]:
        if process.stdout is None:
            raise RuntimeError("Chrome MCP stdout is unavailable")
        ready, _, _ = select.select([process.stdout], [], [], timeout_sec)
        if not ready:
            raise TimeoutError(
                f"Chrome MCP response timed out after {timeout_sec:.1f}s; "
                f"stderr={list(self._stderr_lines)[-5:]}"
            )
        line = process.stdout.readline()
        if not line:
            rc = process.poll()
            _LOGGER.warning(
                "SHIM_EOF: pid=%s poll_rc=%s stderr_tail=%s",
                process.pid,
                rc,
                list(self._stderr_lines)[-5:],
            )
            raise _TransportDeadError(
                f"Chrome MCP transport closed; pid={process.pid} rc={rc} "
                f"stderr={list(self._stderr_lines)[-5:]}"
            )
        payload = json.loads(line)
        if not isinstance(payload, dict):
            raise RuntimeError(f"Chrome MCP returned non-object payload: {payload}")
        return payload

    def _require_live_process(self) -> subprocess.Popen[str]:
        process = self._process
        if process is not None and process.poll() is None:
            return process
        if process is not None and process.poll() is not None:
            _LOGGER.warning(
                "Chrome MCP transport exited rc=%s; stderr tail=%s",
                process.poll(),
                list(self._stderr_lines)[-5:],
            )
        raise _TransportDeadError(
            "Chrome MCP transport unavailable; "
            f"stderr tail={list(self._stderr_lines)[-5:]}"
        )

    def _drain_stderr(self, stream: TextIO) -> None:
        for line in stream:
            self._stderr_lines.append(line.rstrip())

    def _wave_command(self, *args: str) -> dict[str, object]:
        result = subprocess.run(
            ["bash", str(self._wave), "--agent", self._agent_id, *args],
            cwd=str(self._monorepo_root),
            capture_output=True,
            text=True,
            timeout=_wave_command_timeout_sec(),
            check=False,
            env=os.environ.copy(),
        )
        if result.returncode != 0:
            raise RuntimeError(f"Wave command failed: {result.stderr or result.stdout}")
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise RuntimeError(
                f"Wave command returned invalid payload: {result.stdout}"
            )
        return payload

    def _ensure_wave_open(self) -> None:
        result = subprocess.run(
            ["bash", str(self._wave), "status"],
            cwd=str(self._monorepo_root),
            capture_output=True,
            text=True,
            timeout=_wave_command_timeout_sec(),
            check=False,
            env=os.environ.copy(),
        )
        payload: dict[str, object] = {}
        if result.returncode == 0:
            try:
                parsed: object = json.loads(result.stdout)
                if isinstance(parsed, dict):
                    payload = parsed
            except json.JSONDecodeError:
                pass
        wave = payload.get("wave")
        wave_open = isinstance(wave, dict) and wave.get("status") == "open"
        if self._parent_lease_id:
            active = payload.get("activeLeases")
            parent_active = isinstance(active, list) and any(
                isinstance(lease, dict)
                and lease.get("leaseId") == self._parent_lease_id
                and lease.get("agentId") == self._agent_id
                for lease in active
            )
            if wave_open and parent_active:
                return
            raise RuntimeError(
                "PARENT_LEASE_NOT_ACTIVE: refusing to reopen Wave from page client; "
                f"leaseId={self._parent_lease_id}"
            )
        if wave_open:
            return
        try:
            self._wave_command("open")
        except RuntimeError as exc:
            if "WAVE_ALREADY_OPEN" not in str(exc):
                raise

    def _acquire_page_lease(self) -> str:
        self._ensure_wave_open()
        args = ["lease", "acquire", "READ", "--ttl", str(_PAGE_LEASE_TTL_SEC)]
        if self._parent_lease_id:
            args.extend(["--parent-lease-id", self._parent_lease_id])
        last_error: RuntimeError | None = None
        for attempt in range(2):
            try:
                payload = self._wave_command(*args)
            except RuntimeError as exc:
                last_error = exc
                if "RUNTIME_DRIFT" in str(exc) and attempt == 0:
                    try:
                        self._wave_command("reap")
                    except (RuntimeError, TimeoutError):
                        pass
                    continue
                raise
            lease = payload.get("lease")
            lease_id = lease.get("leaseId") if isinstance(lease, dict) else None
            if not isinstance(lease_id, str) or not lease_id:
                raise RuntimeError(f"Wave acquire did not return leaseId: {payload}")
            return lease_id
        if last_error is not None:
            raise last_error
        raise RuntimeError("Wave acquire failed without error detail")

    def _reclaim_stale_browser_context(
        self, context_id: str, *, holder_lease_id: str
    ) -> None:
        try:
            self._wave_command("reap")
        except (RuntimeError, TimeoutError):
            pass
        status = self._wave_command("status")
        active = status.get("activeLeases")
        if not isinstance(active, list):
            return
        for lease in active:
            if not isinstance(lease, dict):
                continue
            lease_id = lease.get("leaseId")
            if (
                lease.get("contextId") != context_id
                or not isinstance(lease_id, str)
                or lease_id == holder_lease_id
            ):
                continue
            if lease.get("pageId"):
                try:
                    self._wave_command("lease", "unbind-browser", lease_id)
                except (RuntimeError, TimeoutError):
                    pass
            try:
                self._wave_command("lease", "release", lease_id)
            except (RuntimeError, TimeoutError):
                pass

    def _bind_page_lease(self, page: McpPage) -> None:
        args = [
            "lease",
            "bind-browser",
            page.lease_id,
            str(page.page_id),
            "--target-id",
            page.target_id,
        ]
        if page.context_id is not None:
            args.extend(("--context-id", page.context_id))
        try:
            self._wave_command(*args)
        except RuntimeError as exc:
            if "BROWSER_CONTEXT_CONFLICT" not in str(exc):
                raise
            if page.context_id is not None:
                self._reclaim_stale_browser_context(
                    page.context_id, holder_lease_id=page.lease_id
                )
            try:
                self._wave_command("lease", "unbind-browser", page.lease_id)
            except (RuntimeError, TimeoutError):
                pass
            self._wave_command(*args)

    def _release_page_lease(self, page: McpPage, *, unbind: bool) -> None:
        errors: list[str] = []
        if unbind:
            try:
                self._wave_command("lease", "unbind-browser", page.lease_id)
            except (RuntimeError, TimeoutError) as exc:
                if not _is_benign_cleanup_error(str(exc)):
                    errors.append(f"unbind: {exc}")
        try:
            self._release_lease(page.lease_id, close_wave_if_idle=False)
        except (RuntimeError, TimeoutError) as exc:
            if not _is_benign_cleanup_error(str(exc)):
                errors.append(f"release: {exc}")
        if errors:
            raise RuntimeError("; ".join(errors))

    def _release_lease(
        self, lease_id: str, *, close_wave_if_idle: bool = False
    ) -> None:
        if close_wave_if_idle:
            self._wave_command("lease", "release", lease_id, "--close-wave-if-idle")
        else:
            self._wave_command("lease", "release", lease_id)

    def _find_page_by_lease(self, lease_id: str) -> McpPage | None:
        for pool in (self._pages, self._disconnected_pages):
            for page in pool.values():
                if page.lease_id == lease_id:
                    return page
        return None

    def _recover_page_lease(self, stale_lease_id: str) -> None:
        page = self._find_page_by_lease(stale_lease_id)
        self._page_lease_heartbeat.untrack(stale_lease_id)
        if page is not None:
            try:
                self._wave_command("lease", "unbind-browser", stale_lease_id)
            except (RuntimeError, TimeoutError) as exc:
                if not _is_benign_cleanup_error(str(exc)):
                    _LOGGER.warning("Stale page lease unbind failed: %s", exc)
        try:
            self._release_lease(stale_lease_id, close_wave_if_idle=False)
        except (RuntimeError, TimeoutError) as exc:
            if not _is_benign_cleanup_error(str(exc)):
                _LOGGER.warning("Stale page lease release failed: %s", exc)
        if page is None:
            return
        new_lease_id = self._acquire_page_lease()
        new_page = McpPage(
            page_id=page.page_id,
            target_id=page.target_id,
            lease_id=new_lease_id,
            context_id=page.context_id,
            url=page.url,
        )
        self._bind_page_lease(new_page)
        self._pages[page.page_id] = new_page
        self._page_lease_heartbeat.track(new_lease_id)
        self._wave_command(
            "lease", "heartbeat", new_lease_id, "--extend", str(_PAGE_LEASE_TTL_SEC)
        )

    def _heartbeat_lease(self, lease_id: str) -> None:
        try:
            self._wave_command(
                "lease", "heartbeat", lease_id, "--extend", str(_PAGE_LEASE_TTL_SEC)
            )
        except (RuntimeError, TimeoutError) as exc:
            message = str(exc)
            if _is_benign_cleanup_error(message):
                self._recover_page_lease(lease_id)
                return
            raise
