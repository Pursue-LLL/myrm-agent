"""Synchronous Chrome DevTools MCP mux client for formal UI E2E runners.

[INPUT]
chrome_mcp_errors (POS: MCP 错误分类谓词)
mcp_protocol (POS: JSON-RPC 解析与 tool 响应提取)
mcp_page_lease_heartbeat (POS: page lease 心跳管理)
cdp_chat_support (POS: E2E API/chat 消息 SSOT)
dev_gate_contract (POS: Dev Gate v2 合约常量 SSOT)
mux_load (POS: mux context / wave lease 负载探针)
mux_upstream_admission (POS: mux cold attach 准入)

[OUTPUT]
ChromeMcpClient: 同步 MCP JSON-RPC 客户端（shim 进程管理、transport recovery、generation check、page lease）
McpPage: MCP 页面句柄（targetId + client 引用）
_TransportDeadError: transport 层统一异常（_read EOF / _write BrokenPipe / 进程退出）

[POS]
正式 pytest UI E2E 的 MCP JSON-RPC 通信层。管理 shim 子进程生命周期，
提供 transport-level 容错（_TransportDeadError → recover）、generation-based 竞态防护、
page lease 心跳，供 mcp_chat_ui / cdp_chat_* 调用。
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
import urllib.error
import urllib.request
import uuid
from builtins import BaseExceptionGroup, ExceptionGroup
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
from urllib.parse import urlsplit

from chrome_mcp_errors import (
    is_benign_cleanup_error as _is_benign_cleanup_error,
    is_context_reset_error as is_context_reset_error,
    is_page_ownership_error as is_page_ownership_error,
    is_page_ownership_error_message as _is_page_ownership_error,
    is_transient_mux_error as _is_transient_mux_error,
)
from mcp_page_lease_heartbeat import PageLeaseHeartbeat
from mcp_protocol import (
    is_retryable_incomplete_new_page_error,
    parse_evaluate_result,
    parse_new_page,
    text_content,
)

_STALE_MUX_PAGE_TOKEN = "No McpPage found for the given page"


def _should_recover_mux_after_tool_error(
    name: str,
    message: str,
    *,
    retry_tools: frozenset[str],
) -> bool:
    if _is_transient_mux_error(message):
        return True
    if name == "new_page" and _STALE_MUX_PAGE_TOKEN in message:
        return True
    return name in retry_tools and "timeout" in message.lower()


from cdp_chat_support import (
    e2e_runtime_binding,
    e2e_runtime_binding_source,
    e2e_runtime_bootstrap_apply_js,
    wait_e2e_provider_ready,
)
from dev_gate_contract import (
    LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
    MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN,
    MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC,
    MUX_RECLAIM_STALL_TOKEN,
    NEW_PAGE_TOOL_RETRY_ATTEMPTS,
    TOOL_RETRY_ATTEMPTS,
)
from mux_load import (
    MuxLoadSnapshot,
    adaptive_page_timeout_ms,
    adaptive_tool_timeout_sec,
    new_page_stagger_sec,
    snapshot_mux_load,
)
from mux_upstream_admission import upstream_cold_attach_slot

_CLEANUP_TIMEOUT_SEC = 15.0
_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC = LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC
_MCP_READ_POLL_SEC = _LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC
_TOOL_RETRY_ATTEMPTS = TOOL_RETRY_ATTEMPTS
_NEW_PAGE_TOOL_RETRY_ATTEMPTS = NEW_PAGE_TOOL_RETRY_ATTEMPTS
_PAGE_LEASE_TTL_SEC = int(os.environ.get("MYRM_PAGE_LEASE_TTL_SEC", "600"))


def _is_mux_parallel_fail_fast_message(message: str) -> bool:
    from transport_supervisor import MUX_TRANSPORT_EXHAUSTED_TOKEN

    return (
        MUX_RECLAIM_STALL_TOKEN in message
        or MUX_TRANSPORT_EXHAUSTED_TOKEN in message
        or MUX_CROSS_SESSION_RECOVER_DENIED_TOKEN in message
    )


def _parallel_mux_peer_count() -> int:
    """Active parallel mux/wave peers for cross-session teardown guard (R69/TRSM)."""
    snapshot = snapshot_mux_load(force=True)
    wave_leases = max(0, snapshot.wave_leases)
    mux_contexts = max(0, snapshot.mux_contexts)
    daemon_count = 1
    try:
        from runtime_probe import mux_owned_daemon_count

        daemon_count = max(1, int(mux_owned_daemon_count()))
    except (ImportError, OSError, TypeError, ValueError):
        pass
    return max(wave_leases, mux_contexts, daemon_count)


def _shim_process_alive(client: "ChromeMcpClient") -> bool:
    process = client._process
    return process is not None and process.poll() is None

def _reclaim_wall_deadline() -> float:
    return time.monotonic() + float(MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC)


def _remaining_reclaim_sec(deadline: float) -> float:
    return max(0.0, deadline - time.monotonic())


def _raise_mux_reclaim_stall(phase: str, *, started: float) -> None:
    elapsed = time.monotonic() - started
    raise RuntimeError(
        f"{MUX_RECLAIM_STALL_TOKEN}: {phase} blocked for {elapsed:.1f}s "
        f"(cap={MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC}s); recover mux and retry"
    )


def _check_mux_reclaim_deadline(deadline: float, phase: str, *, started: float) -> None:
    if time.monotonic() >= deadline:
        _raise_mux_reclaim_stall(phase, started=started)


_PAGE_LEASE_HEARTBEAT_INTERVAL_SEC = 30.0
_TRANSPORT_RECOVER_ATTEMPTS = 3
_REQUEST_LOCK_ACQUIRE_SEC = 5.0
_REQUEST_LOCK_ACQUIRE_PARALLEL_CAP_SEC = 90.0
_EXPLICIT_SHORT_TOOL_TIMEOUT_CEILING_SEC = 30.0
_LOGGER = logging.getLogger(__name__)


def _resolve_request_lock_acquire_sec() -> float:
    """Scale per-session mux request lock wait with parallel E2E load (R76).

    ``transport_supervisor.recovery_lock_wait_sec`` scales on active pytest count;
    ``_parallel_mux_peer_count`` scales on concurrent mux sessions (Run#20:
    active_tests=1 but peers=5 → 35s wait was insufficient). Stream lock holder
    (shared_hot desktop) uses full parallel cap — sole authorized shared_hot consumer.
    """
    scaled = _REQUEST_LOCK_ACQUIRE_SEC
    try:
        from transport_supervisor import recovery_lock_wait_sec

        scaled = max(scaled, recovery_lock_wait_sec())
    except ImportError:
        pass
    peer_count = _parallel_mux_peer_count()
    if peer_count > 1:
        peer_scaled = _REQUEST_LOCK_ACQUIRE_SEC + (peer_count - 1) * 15.0
        scaled = max(scaled, peer_scaled)
    if os.environ.get("MYRM_E2E_STREAM_LOCK_HELD", "").strip() == "1":
        return _REQUEST_LOCK_ACQUIRE_PARALLEL_CAP_SEC
    return min(
        max(_REQUEST_LOCK_ACQUIRE_SEC, scaled),
        _REQUEST_LOCK_ACQUIRE_PARALLEL_CAP_SEC,
    )


class _TransportDeadError(RuntimeError):
    """Raised when the MCP shim process is missing, exited, or its stdio pipe closed.

    All transport-level failures (_read EOF, _write BrokenPipe, process poll ≠ None)
    MUST use this type so ``_request`` can catch and trigger ``_recover_mux_transport``.
    Application-level errors (tool failures, protocol errors) use plain RuntimeError.
    """


def _chrome_e2e_port() -> int:
    raw = os.environ.get("MYRM_CHROME_E2E_PORT", "9333").strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 9333


def _http_close_exact_target(target_id: str) -> bool:
    target = target_id.strip()
    if not target:
        return False
    url = f"http://127.0.0.1:{_chrome_e2e_port()}/json/close/{target}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            response.read()
        return True
    except urllib.error.HTTPError as exc:
        return exc.code == 404
    except (OSError, urllib.error.URLError):
        return False


def _tool_retry_attempts(tool_name: str) -> int:
    if tool_name == "new_page":
        return _NEW_PAGE_TOOL_RETRY_ATTEMPTS
    return _TOOL_RETRY_ATTEMPTS


def _tool_retry_backoff_sec(tool_name: str, attempt: int, *, transient: bool) -> float:
    base = 0.5 * (attempt + 1)
    if tool_name == "new_page":
        base = max(base, 1.0 * (attempt + 1))
    if transient:
        base += 0.75 * (attempt + 1)
    return base


def _wave_command_timeout_sec() -> float:
    override = os.environ.get("MYRM_WAVE_CMD_TIMEOUT_SEC", "").strip()
    if override:
        return float(override)
    if os.environ.get("MYRM_E2E_LEASE_ID", "").strip():
        return 120.0
    return 10.0


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
        self._request_lock = threading.RLock()
        self._stderr_lines: deque[str] = deque(maxlen=100)
        self._stderr_thread: threading.Thread | None = None
        self._pages: dict[int, McpPage] = {}
        self._disconnected_pages: dict[int, McpPage] = {}
        self._page_lease_heartbeat = PageLeaseHeartbeat(
            self._heartbeat_lease,
            interval_sec=_PAGE_LEASE_HEARTBEAT_INTERVAL_SEC,
        )
        self._agent_id = (
            os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
            or os.environ.get("MYRM_WAVE_AGENT_ID", "").strip()
            or f"pytest-mcp:{os.getpid()}:{uuid.uuid4().hex}"
        )
        self._parent_lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
        self._monorepo_root = Path(__file__).resolve().parents[4]
        self._wave = self._monorepo_root / "myrm-agent/scripts/dev/wave.sh"
        self._mux_load_cache: MuxLoadSnapshot | None = None
        self._reclaim_in_progress = False
        self._mux_eval_executor: object | None = None
        self._mux_reset_executor: object | None = None

    def _request_lock_is_held(self) -> bool:
        acquired = self._request_lock.acquire(blocking=False)
        if acquired:
            self._request_lock.release()
            return False
        return True

    @staticmethod
    def _initial_mux_generation() -> int:
        """Bind client generation to runtime cell ledger when SHPOIB slot is active."""
        try:
            from e2e_runtime_cell import current_cell_id, read_cell_mux_generation

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
    ) -> threading.Lock:
        max_wait_sec = _resolve_request_lock_acquire_sec()
        wait_sec = float(timeout_sec) if timeout_sec is not None else max_wait_sec
        wait_sec = max(0.1, min(wait_sec, max_wait_sec))
        lock = self._request_lock
        if not lock.acquire(timeout=wait_sec):
            raise RuntimeError(
                f"{MUX_RECLAIM_STALL_TOKEN}: request lock blocked for {wait_sec:.1f}s"
            )
        return lock

    def _release_request_lock(self, lock: threading.Lock | None = None) -> None:
        target = lock if lock is not None else self._request_lock
        try:
            target.release()
        except RuntimeError:
            # abandon_inflight_requests() may replace _request_lock while orphan
            # threads still hold the previous lock instance.
            pass

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
        from transport_recovery_core import (
            TransportRecoveryMode,
            resolve_transport_recovery_mode,
        )

        return resolve_transport_recovery_mode(
            parallel_peers=_parallel_mux_peer_count(),
            shim_alive=_shim_process_alive(self),
        )

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
        return max(timeout_sec, adaptive)

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
        process = self._process
        if process is not None and process.poll() is None:
            return
        if process is not None:
            self._teardown_shim_process()
        self._spawn_shim_process()
        self._initialize_shim_session()

    def close(self) -> None:
        errors: list[Exception] = []
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
        for attempt in range(5):
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
            transient = "Failed to fetch" in error_text or "fetch" in error_text.lower()
            if attempt < 4 and transient and api_base:
                wait_e2e_provider_ready(
                    api_url=api_base, timeout_sec=bootstrap_timeout_sec
                )
                time.sleep(2.0 * (attempt + 1))
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
        from transport_supervisor import assert_mux_daemons_single

        assert_mux_daemons_single(phase="new_page")
        resolved_timeout_ms = (
            timeout_ms if timeout_ms is not None else self._default_page_timeout_ms()
        )
        context_id = isolated_context.strip() if isolated_context is not None else None
        if isolated_context is not None and not context_id:
            raise ValueError("isolated_context must not be empty")
        lease_id = self._acquire_page_lease()
        page: McpPage | None = None
        runtime_binding = self._runtime_binding_source_for(url)
        with upstream_cold_attach_slot():
            try:
                self._heartbeat_lease(lease_id)
                load = snapshot_mux_load()
                stagger_sec = new_page_stagger_sec(
                    mux_contexts=load.mux_contexts,
                    wave_leases=load.wave_leases,
                    jitter_seed=os.getpid(),
                )
                if stagger_sec > 0:
                    time.sleep(stagger_sec)
                initial_url = "about:blank" if runtime_binding is not None else url
                arguments: dict[str, object] = {
                    "url": initial_url,
                    "timeout": resolved_timeout_ms,
                }
                if context_id is not None:
                    arguments["isolatedContext"] = context_id
                page_id: int
                target_id: str
                new_page_result: dict[str, object] | None = None
                for parse_attempt in range(_NEW_PAGE_TOOL_RETRY_ATTEMPTS):
                    try:
                        new_page_result = self.call_tool(
                            "new_page",
                            arguments,
                            timeout_sec=self._resolve_tool_timeout_sec(
                                min(
                                    resolved_timeout_ms / 1000 + 5,
                                    self._request_timeout_sec,
                                ),
                                page_timeout_ms=resolved_timeout_ms,
                            ),
                        )
                        page_id, target_id = parse_new_page(new_page_result)
                        break
                    except RuntimeError as exc:
                        if not is_retryable_incomplete_new_page_error(
                            exc, new_page_result
                        ):
                            raise
                        if parse_attempt + 1 >= _NEW_PAGE_TOOL_RETRY_ATTEMPTS:
                            raise
                        self._recover_mux_transport()
                        time.sleep(
                            _tool_retry_backoff_sec(
                                "new_page", parse_attempt, transient=True
                            )
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
        self._pages.pop(page.page_id, None)
        self._disconnected_pages.pop(page.page_id, None)
        try:
            self._release_page_lease(page, unbind=not errors)
        except (RuntimeError, TimeoutError) as exc:
            errors.append(f"release lease: {exc}")
        if not errors:
            return
        message = "Chrome MCP page cleanup failed: " + "; ".join(errors)
        if ignore_errors or all(_is_benign_cleanup_error(part) for part in errors):
            _LOGGER.warning(message)
            return
        raise RuntimeError(message)

    def _resolve_page(self, page: McpPage) -> McpPage:
        tracked = self._pages.get(page.page_id)
        if tracked is not None:
            return tracked
        for pages in (self._pages, self._disconnected_pages):
            for candidate in pages.values():
                if candidate.lease_id == page.lease_id:
                    return candidate
        return page

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
        fresh = self.new_page(fallback_url, timeout_ms)
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
        from transport_recovery_core import TransportRecoveryMode

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
            from e2e_runtime_cell import bump_cell_mux_generation, current_cell_id

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
        self, page: McpPage, expression: str, *, timeout_sec: float = 15.0
    ) -> object:
        resolved = self._resolve_page(page)
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
                raise
        raise RuntimeError("Chrome MCP evaluate exhausted reload attempts")

    def navigate(
        self,
        page: McpPage,
        url: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
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
                timeout_sec=self._resolve_tool_timeout_sec(
                    min(resolved_timeout_ms / 1000 + 5, self._request_timeout_sec),
                    page_timeout_ms=resolved_timeout_ms,
                ),
            )

        try:
            _navigate_resolved(resolved)
        except RuntimeError as exc:
            if _is_page_ownership_error(str(exc)):
                resolved = self.reclaim_owned_page(resolved)
                _navigate_resolved(resolved)
            elif "timeout" not in str(exc).lower():
                raise
            else:
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

    def reload(self, page: McpPage, *, timeout_ms: int = 15_000) -> None:
        resolved = self._resolve_page(page)
        self.call_tool(
            "navigate_page",
            {"pageId": resolved.page_id, "type": "reload", "timeout": timeout_ms},
            timeout_sec=min(timeout_ms / 1000 + 5, self._request_timeout_sec),
        )

    def press_key(self, page: McpPage, key: str) -> None:
        resolved = self._resolve_page(page)
        self.call_tool(
            "press_key",
            {"pageId": resolved.page_id, "key": key},
            timeout_sec=_LIVE_AGENT_TOOL_MIN_TIMEOUT_SEC,
        )

    def type_text(self, page: McpPage, text: str) -> None:
        resolved = self._resolve_page(page)
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
            # Nested reclaim during orphan recovery — return page; caller will retry or fail fast.
            return page
        self._reclaim_depth = depth + 1
        try:
            return self._reopen_owned_page_inner(page)
        finally:
            self._reclaim_depth = depth

    def _reopen_owned_page_inner(self, page: McpPage) -> McpPage:
        reclaim_deadline = _reclaim_wall_deadline()
        reclaim_started = time.monotonic()
        self._ensure_shim_transport()
        _check_mux_reclaim_deadline(
            reclaim_deadline, "reopen_start", started=reclaim_started
        )
        reopen_url = (page.url or "http://127.0.0.1:3000").strip()
        runtime_binding = self._runtime_binding_source_for(reopen_url)
        old_target_id = page.target_id.strip()
        if old_target_id and not _http_close_exact_target(old_target_id):
            raise RuntimeError(
                f"Chrome MCP reopen failed: could not close previous targetId={old_target_id}"
            )
        self._pages.pop(page.page_id, None)
        initial_url = "about:blank" if runtime_binding is not None else reopen_url
        arguments: dict[str, object] = {"url": initial_url, "timeout": 120_000}
        if page.context_id is not None:
            arguments["isolatedContext"] = page.context_id
        remaining = _remaining_reclaim_sec(reclaim_deadline)
        _check_mux_reclaim_deadline(
            reclaim_deadline, "new_page", started=reclaim_started
        )
        with upstream_cold_attach_slot():
            result = self.call_tool(
                "new_page",
                arguments,
                timeout_sec=min(
                    125.0,
                    self._request_timeout_sec,
                    remaining,
                ),
            )
        page_id, target_id = parse_new_page(result)
        lease_id = page.lease_id
        reopened = McpPage(
            page_id=page_id,
            target_id=target_id,
            lease_id=lease_id,
            context_id=page.context_id,
            url=reopen_url,
        )
        self._heartbeat_lease(lease_id)
        try:
            _check_mux_reclaim_deadline(
                reclaim_deadline, "bind_lease", started=reclaim_started
            )
            self._bind_page_lease(reopened)
        except RuntimeError as exc:
            if MUX_RECLAIM_STALL_TOKEN in str(exc):
                raise
            if "LEASE_NOT_ACTIVE" not in str(exc):
                raise
            self._page_lease_heartbeat.untrack(lease_id)
            lease_id = self._acquire_page_lease()
            reopened = McpPage(
                page_id=page_id,
                target_id=target_id,
                lease_id=lease_id,
                context_id=page.context_id,
                url=reopen_url,
            )
            self._heartbeat_lease(lease_id)
            _check_mux_reclaim_deadline(
                reclaim_deadline, "bind_lease_retry", started=reclaim_started
            )
            self._bind_page_lease(reopened)
        self._pages[page_id] = reopened
        self._page_lease_heartbeat.track(lease_id)
        if runtime_binding is not None:
            remaining = _remaining_reclaim_sec(reclaim_deadline)
            _check_mux_reclaim_deadline(
                reclaim_deadline, "runtime_bind", started=reclaim_started
            )
            self._bind_and_navigate_runtime_page(
                reopened,
                reopen_url,
                runtime_binding,
                timeout_ms=min(
                    120_000,
                    int(max(5_000, remaining * 1000)),
                ),
            )
        return reopened

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
        try:
            process = self._require_live_process()
            response = self._exchange_locked(
                process,
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "myrm-pytest-mcp", "version": "1.0"},
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
            self._release_request_lock(held_lock)
        self._page_lease_heartbeat.start()

    def _recover_mux_transport(self, *, start_generation: int | None = None) -> None:
        from transport_supervisor import mux_recovery_scope

        with mux_recovery_scope(phase="recover_mux_transport"):
            self._recover_mux_transport_inner(start_generation=start_generation)

    def _recover_mux_transport_inner(
        self, *, start_generation: int | None = None
    ) -> None:
        held_lock = self._acquire_request_lock()
        try:
            _LOGGER.warning(
                "RECOVER_MUX_TRANSPORT: gen=%s pages=%d disconnected=%d",
                start_generation,
                len(self._pages),
                len(self._disconnected_pages),
            )
            reclaim_deadline = _reclaim_wall_deadline()
            saved_pages = self._collapse_pages_for_recovery(
                {**self._disconnected_pages, **self._pages}
            )
            from transport_recovery_core import (
                TRSM_MODE_TOKEN,
                TransportRecoveryMode,
            )

            trsm_mode = self._resolve_trsm_mode()
            peer_count = _parallel_mux_peer_count()
            _LOGGER.warning(
                "%s=%s parallel_mux_peers=%d pages=%d",
                TRSM_MODE_TOKEN,
                trsm_mode.value,
                peer_count,
                len(saved_pages),
            )
            if trsm_mode == TransportRecoveryMode.PARALLEL_PAGE_RECLAIM:
                self._reclaim_pages_parallel_safe(saved_pages, reclaim_deadline)
                return
            self._teardown_shim_process()
            last_error: RuntimeError | None = None
            for attempt in range(_TRANSPORT_RECOVER_ATTEMPTS):
                if (
                    start_generation is not None
                    and start_generation != self._request_generation
                ):
                    raise RuntimeError(
                        f"{MUX_RECLAIM_STALL_TOKEN}: request abandoned during "
                        f"transport recovery (orphan recovery in progress)"
                    )
                _check_mux_reclaim_deadline(
                    reclaim_deadline,
                    "recover_mux_transport",
                    started=reclaim_deadline - float(MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC),
                )
                try:
                    self._spawn_shim_process()
                    self._initialize_shim_session()
                    break
                except RuntimeError as exc:
                    last_error = exc
                    self._teardown_shim_process()
                    if attempt + 1 < _TRANSPORT_RECOVER_ATTEMPTS:
                        time.sleep(
                            min(
                                0.75 * (attempt + 1),
                                _remaining_reclaim_sec(reclaim_deadline),
                            )
                        )
            else:
                if last_error is not None:
                    raise last_error
                _check_mux_reclaim_deadline(
                    reclaim_deadline,
                    "recover_mux_transport",
                    started=reclaim_deadline - float(MUX_PAGE_RECLAIM_HARD_TIMEOUT_SEC),
                )
                return
            if not saved_pages:
                return
            self._rebuild_disconnected_pages(saved_pages, reclaim_deadline)
        finally:
            self._release_request_lock(held_lock)

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
        page_items = list(saved_pages.items())
        for idx, (old_page_id, old_page) in enumerate(page_items):
            remaining = _remaining_reclaim_sec(reclaim_deadline)
            if remaining < 5.0:
                _LOGGER.warning(
                    "page rebuild budget exhausted; %d pages remain disconnected",
                    len(page_items) - idx,
                )
                break
            new_page_id: int | None = None
            try:
                old_target = old_page.target_id.strip()
                if old_target:
                    _http_close_exact_target(old_target)
                reopen_url = (old_page.url or "http://127.0.0.1:3000").strip()
                runtime_binding = self._runtime_binding_source_for(reopen_url)
                initial_url = (
                    "about:blank" if runtime_binding is not None else reopen_url
                )
                arguments: dict[str, object] = {"url": initial_url, "timeout": 60_000}
                if old_page.context_id is not None:
                    arguments["isolatedContext"] = old_page.context_id
                result = self._call_tool_direct(
                    "new_page", arguments, timeout_sec=min(65.0, remaining)
                )
                page_id, target_id = parse_new_page(result)
                new_page_id = page_id
                rebuilt = McpPage(
                    page_id=page_id,
                    target_id=target_id,
                    lease_id=old_page.lease_id,
                    context_id=old_page.context_id,
                    url=reopen_url,
                )
                self._heartbeat_lease(old_page.lease_id)
                self._bind_page_lease(rebuilt)
                if runtime_binding is not None:
                    self._bind_and_navigate_runtime_page(
                        rebuilt,
                        reopen_url,
                        runtime_binding,
                        timeout_ms=min(60_000, int(remaining * 1000)),
                    )
                self._pages[page_id] = rebuilt
                self._disconnected_pages.pop(old_page_id, None)
                self._page_lease_heartbeat.track(old_page.lease_id)
                _LOGGER.info(
                    "rebuilt page %d→%d (url=%s) after transport recovery",
                    old_page_id,
                    page_id,
                    reopen_url,
                )
            except Exception as exc:
                _LOGGER.warning(
                    "failed to rebuild page %d after transport recovery: %s",
                    old_page_id,
                    exc,
                )
                self._disconnected_pages.pop(old_page_id, None)
                if new_page_id is not None:
                    self._pages.pop(new_page_id, None)
                    try:
                        self._call_tool_direct(
                            "close_page",
                            {"pageId": new_page_id},
                            timeout_sec=10.0,
                        )
                    except Exception:
                        pass

    def _reclaim_pages_parallel_safe(
        self,
        saved_pages: dict[int, McpPage],
        reclaim_deadline: float,
    ) -> None:
        """R69-C: page-level reclaim when global shim teardown would harm peer sessions."""
        if not saved_pages:
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

    def abandon_inflight_requests(self) -> None:
        """Invalidate orphaned mux I/O after asyncio cancelled a blocking evaluate thread."""
        _LOGGER.warning(
            "ABANDON_INFLIGHT: gen=%d→%d",
            self._request_generation,
            self._request_generation + 1,
        )
        self._request_generation += 1
        try:
            from e2e_runtime_cell import current_cell_id, persist_cell_mux_generation

            if current_cell_id():
                persist_cell_mux_generation(self._request_generation)
        except ImportError:
            pass
        self._page_lease_heartbeat.stop()
        self._reclaim_in_progress = False
        from transport_recovery_core import TRSM_MODE_TOKEN, should_skip_global_teardown

        trsm_mode = self._resolve_trsm_mode()
        if should_skip_global_teardown(trsm_mode):
            _LOGGER.warning(
                "ABANDON_INFLIGHT_SKIPPED_TEARDOWN: %s=%s parallel_mux_peers=%d",
                TRSM_MODE_TOKEN,
                trsm_mode.value,
                _parallel_mux_peer_count(),
            )
        else:
            self._teardown_shim_process()
        # Orphan to_thread may still hold the old lock in select(); replace so recover
        # on the event loop thread cannot deadlock (R49-R50).
        self._request_lock = threading.RLock()

    def reset_after_orphan(self) -> None:
        """Single orphan recovery entry: invalidate in-flight mux I/O and restart transport."""
        self.abandon_inflight_requests()
        self._recover_mux_transport()

    def recover_mux_transport(self) -> None:
        """Restart MCP shim after mux timeout or transport drift (E2E orchestrator hook)."""
        if not self._request_lock.acquire(blocking=False):
            self.reset_after_orphan()
            return
        self._request_lock.release()
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
        for attempt in range(max_attempts):
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
                    time.sleep(
                        _tool_retry_backoff_sec(name, attempt, transient=True)
                    )
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
                if not is_probe:
                    if (
                        transient and not _is_page_ownership_error(message)
                    ) or stale_mux_page:
                        self._recover_mux_transport()
                    elif timed_out and name in retry_tools and attempt >= 1:
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
                    time.sleep(
                        _tool_retry_backoff_sec(name, attempt, transient=True)
                    )
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
                    time.sleep(
                        _tool_retry_backoff_sec(name, attempt, transient=True)
                    )
                    continue
                if not is_probe and _should_recover_mux_after_tool_error(
                    name, message, retry_tools=frozenset(retry_tools)
                ):
                    last_error = RuntimeError(f"Chrome MCP {name} failed: {message}")
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
