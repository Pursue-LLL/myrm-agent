"""E2E page lifecycle via Browser Orchestrator daemon (P0-B fail-closed path).

Used when ``MYRM_BROWSER_ORCHESTRATOR=1`` — no mux MCP fallback.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from browser_orchestrator_client import BrowserOrchestratorClient
from cdp_chat_support import (
    e2e_api_base_inject_js,
    e2e_private_api_ready_timeout_sec,
    e2e_runtime_binding_source,
    get_e2e_api_url,
    get_open_page_api_url,
    wait_e2e_provider_ready,
)


@dataclass
class OrchestratorMcpPage:
    page_id: int
    target_id: str
    lease_id: str = ""
    context_id: str | None = None
    url: str | None = None


class OrchestratorChromeClient:
    """Minimal ChromeMcpClient duck-type for READ smokes over the daemon."""

    def __init__(
        self,
        *,
        session_id: str,
        daemon: BrowserOrchestratorClient,
        request_timeout_sec: float = 180.0,
    ) -> None:
        self._session_id = session_id
        self._daemon = daemon
        self._request_timeout_sec = request_timeout_sec
        self._primary_page: OrchestratorMcpPage | None = None

    def bind_primary_page(self, page: OrchestratorMcpPage) -> None:
        self._primary_page = page

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

    def set_tool_wall_deadline(self, _deadline: float | None) -> None:
        return None

    def mux_eval_executor(self) -> object | None:
        return None

    def mux_reset_executor(self) -> object | None:
        return None

    def discard_mux_reset_executor(self) -> None:
        return None

    def reset_after_orphan(self) -> None:
        """Re-open primary page after mux orphan (orchestrator has no mux transport)."""
        if self._primary_page is None:
            return
        page = self._primary_page
        try:
            self._daemon.evaluate_page(
                self._session_id,
                page.target_id,
                "(() => true)()",
                timeout_sec=5.0,
            )
            return
        except (TimeoutError, OSError, RuntimeError):
            pass
        fallback = page.url or "http://127.0.0.1:3000/"
        self._reopen_primary_page(fallback, page=page)

    def _is_terminal_tab_error(self, message: str) -> bool:
        return "E2E_USER_CLOSED_TAB" in message

    def _is_missing_session_context(self, message: str) -> bool:
        lowered = message.lower()
        return (
            "no context for session" in lowered
            or "mux_context_disconnected" in lowered
            or "session with given id not found" in lowered
            or "does not own target" in lowered
            or "no target with given id" in lowered
        )

    def _ensure_session_context(self) -> None:
        try:
            self._daemon.destroy_session(self._session_id)
        except (RuntimeError, TimeoutError, OSError):
            pass
        try:
            self._daemon.create_session(self._session_id)
        except RuntimeError as exc:
            if "already" not in str(exc).lower():
                raise

    def _reopen_primary_page(
        self, url: str, *, page: OrchestratorMcpPage | None = None
    ) -> OrchestratorMcpPage:
        orphan_timeout_sec = min(45.0, self._request_timeout_sec)
        last_exc: BaseException | None = None
        hot_eligible = False
        try:
            from warm_shell_registry import shared_read_hot_path_decision

            hot_eligible = shared_read_hot_path_decision(url=url).eligible
        except ImportError:
            hot_eligible = False
        for attempt in range(1, 3):
            try:
                self._ensure_session_context()
                with self._daemon.bounded_request_timeout(orphan_timeout_sec):
                    if hot_eligible:
                        created = self._daemon.create_page(
                            self._session_id,
                            url=url,
                        )
                    else:
                        created = self._daemon.open_page_transaction(
                            self._session_id,
                            url=url,
                        )
                live = OrchestratorMcpPage(
                    page_id=int(created["pageId"]),
                    target_id=str(created["targetId"]),
                    url=str(created.get("url", url)),
                )
                if page is not None:
                    page.page_id = live.page_id
                    page.target_id = live.target_id
                    page.url = live.url
                    self._primary_page = page
                    return page
                self._primary_page = live
                return live
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_exc = exc
                message = str(exc)
                if self._is_missing_session_context(message):
                    self._ensure_session_context()
                    continue
                if self._recover_daemon_if_needed(message):
                    continue
                if attempt >= 2:
                    break
                time.sleep(min(2.0 * float(attempt), 4.0))
        try:
            self._ensure_session_context()
            with self._daemon.bounded_request_timeout(orphan_timeout_sec):
                created = self._daemon.create_page(self._session_id, url)
            live = OrchestratorMcpPage(
                page_id=int(created["pageId"]),
                target_id=str(created["targetId"]),
                url=url,
            )
            if page is not None:
                page.page_id = live.page_id
                page.target_id = live.target_id
                page.url = live.url
                self._primary_page = page
                return page
            self._primary_page = live
            return live
        except (TimeoutError, OSError, RuntimeError):
            if last_exc is not None:
                raise last_exc
            raise

    def primary_owned_page(self) -> OrchestratorMcpPage | None:
        return self._primary_page

    def ensure_primary_page_after_recovery(
        self,
        *,
        fallback_url: str,
        timeout_ms: int = 120_000,
    ) -> OrchestratorMcpPage:
        del timeout_ms
        existing = self._primary_page
        if existing is not None:
            return existing
        fresh = self.new_page(fallback_url)
        self._primary_page = fresh
        return fresh

    def reclaim_owned_page(self, page: OrchestratorMcpPage) -> OrchestratorMcpPage:
        try:
            self._daemon.evaluate_page(
                self._session_id,
                page.target_id,
                "(() => true)()",
                timeout_sec=5.0,
            )
            return page
        except RuntimeError as exc:
            if not self._is_terminal_tab_error(str(exc)):
                raise
        fallback = page.url or "http://127.0.0.1:3000/"
        return self._reopen_primary_page(fallback, page=page)

    def new_page(
        self,
        url: str,
        *,
        timeout_ms: int | None = None,
        isolated_context: str | None = None,
    ) -> OrchestratorMcpPage:
        del timeout_ms, isolated_context
        created = self._daemon.open_page_transaction(self._session_id, url=url)
        page = OrchestratorMcpPage(
            page_id=int(created["pageId"]),
            target_id=str(created["targetId"]),
            url=str(created.get("url", url)),
        )
        self._primary_page = page
        return page

    def type_text(self, page: OrchestratorMcpPage, text: str) -> None:
        escaped = json.dumps(text)
        self.evaluate(
            page,
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
            timeout_sec=15.0,
        )

    def press_key(self, page: OrchestratorMcpPage, key: str) -> None:
        key_literal = json.dumps(key)
        self.evaluate(
            page,
            f"""(() => {{
              const el = document.activeElement ?? document.body;
              el.dispatchEvent(new KeyboardEvent('keydown', {{ key: {key_literal}, bubbles: true }}));
              el.dispatchEvent(new KeyboardEvent('keyup', {{ key: {key_literal}, bubbles: true }}));
              return {{ ok: true }};
            }})()""",
            timeout_sec=15.0,
        )

    def _is_retryable_transport_error(self, message: str) -> bool:
        lowered = message.lower()
        return (
            "browser orchestrator response timeout" in lowered
            or "cdp request timeout" in lowered
            or "daemon not running" in lowered
            or "connection reset" in lowered
            or "broken pipe" in lowered
            or self._is_missing_session_context(message)
        )

    def _recover_daemon_if_needed(self, message: str) -> bool:
        return _recover_orchestrator_daemon(self._daemon, message, wall_sec=45.0)

    def evaluate(
        self,
        page: OrchestratorMcpPage,
        expression: str,
        *,
        timeout_sec: float = 15.0,
    ) -> object:
        effective = min(max(5.0, timeout_sec), self._request_timeout_sec)
        last_exc: BaseException | None = None
        for attempt in range(1, 6):
            try:
                payload = self._daemon.evaluate_page(
                    self._session_id,
                    page.target_id,
                    expression,
                    timeout_sec=effective,
                )
                return payload.get("value")
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_exc = exc
                message = str(exc)
                if self._recover_daemon_if_needed(message):
                    continue
                if self._is_missing_session_context(message):
                    self._ensure_session_context()
                    fallback_url = page.url or "http://127.0.0.1:3000/"
                    self._reopen_primary_page(fallback_url, page=page)
                    continue
                if self._is_terminal_tab_error(message) and attempt < 5:
                    fallback = page.url or "http://127.0.0.1:3000/"
                    try:
                        self._reopen_primary_page(fallback, page=page)
                    except (RuntimeError, TimeoutError, OSError):
                        pass
                    continue
                retryable = self._is_retryable_transport_error(message)
                if not retryable or attempt >= 5:
                    raise
                time.sleep(min(2.0 * float(attempt), 6.0))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Browser Orchestrator evaluate failed without exception")

    def navigate(
        self,
        page: OrchestratorMcpPage,
        url: str,
        *,
        timeout_ms: int | None = None,
    ) -> None:
        _ = timeout_ms
        last_exc: BaseException | None = None
        for attempt in range(1, 4):
            try:
                self._daemon.navigate_page(self._session_id, page.target_id, url)
                page.url = url
                return
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_exc = exc
                message = str(exc)
                if self._recover_daemon_if_needed(message):
                    continue
                if self._is_missing_session_context(message):
                    self._ensure_session_context()
                    continue
                if self._is_terminal_tab_error(message) and attempt < 3:
                    try:
                        from warm_shell_registry import shared_read_hot_path_decision

                        if shared_read_hot_path_decision(url=url).eligible:
                            self._ensure_session_context()
                            created = self._daemon.create_page(
                                self._session_id,
                                url=url,
                            )
                            page.page_id = int(created["pageId"])
                            page.target_id = str(created["targetId"])
                            page.url = url
                            return
                    except ImportError:
                        pass
                    self._reopen_primary_page(url, page=page)
                    continue
                if not self._is_retryable_transport_error(message) or attempt >= 3:
                    raise
                time.sleep(min(2.0 * float(attempt), 6.0))
        if last_exc is not None:
            raise last_exc
        raise RuntimeError("Browser Orchestrator navigate failed without exception")

    def reload(self, page: OrchestratorMcpPage, *, timeout_ms: int = 15_000) -> None:
        eval_timeout = min(30.0, max(5.0, timeout_ms / 1000.0))
        self.evaluate(
            page,
            "(() => { window.location.reload(); return true; })()",
            timeout_sec=eval_timeout,
        )
        binding_source = e2e_runtime_binding_source()
        if binding_source:
            inject_expr = f"(() => {{{binding_source} return true; }})()"
            deadline = time.monotonic() + eval_timeout
            while time.monotonic() < deadline:
                time.sleep(0.5)
                try:
                    self.evaluate(page, inject_expr, timeout_sec=5.0)
                    break
                except Exception:
                    continue


def _resolve_session_id() -> str:
    from dev_gate_contract import E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN
    from chrome_e2e.gates.entry_guard import is_e2e_chrome_mcp_diagnostic_mode

    # Per-lease orch session isolates parallel chrome_e2e (shared MYRM_E2E_RUN_ID is parent-only).
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    if lease_id:
        return f"orch-{lease_id}"
    run_id = os.environ.get("MYRM_E2E_RUN_ID", "").strip()
    if run_id:
        return run_id
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if agent_id:
        return agent_id
    if is_e2e_chrome_mcp_diagnostic_mode():
        return f"orchestrator-diagnostic-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    raise RuntimeError(
        f"{E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN}: MYRM_E2E_LEASE_ID, "
        "MYRM_E2E_AGENT_ID, or MYRM_E2E_RUN_ID required — launch via ./myrm test -m chrome_e2e"
    )


def _monorepo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _orchestrator_daemon_unreachable(message: str) -> bool:
    """True when daemon socket is gone or hung under parallel burst (fix#14)."""
    lowered = message.lower()
    if "daemon not running" in lowered or "connection refused" in lowered:
        return True
    if "browser orchestrator response timeout" in lowered:
        return _effective_parallel_load() >= 2 or not BrowserOrchestratorClient(
            timeout_sec=3.0
        ).is_alive()
    return False


def _recover_orchestrator_daemon(
    daemon: BrowserOrchestratorClient,
    message: str,
    *,
    wall_sec: float = 45.0,
) -> bool:
    if not _orchestrator_daemon_unreachable(message):
        return False
    if not daemon.is_alive():
        _spawn_ensure_orchestrator()
    _wait_orchestrator_daemon_ready(daemon, wall_sec=wall_sec)
    return True


def _spawn_ensure_orchestrator() -> None:
    """Best-effort daemon (re)start — serialized by ensure script flock."""
    script = _monorepo_root() / "scripts/dev/ensure-browser-orchestrator.sh"
    if not script.is_file():
        return
    env = os.environ.copy()
    env["MYRM_BROWSER_ORCHESTRATOR"] = "1"
    if _effective_parallel_load() >= 2:
        env["MYRM_BROWSER_ORCHESTRATOR_ENSURE_DONE"] = "1"
    node_dir = "/opt/homebrew/bin"
    path = env.get("PATH", "")
    if node_dir not in path:
        bun_bin = os.path.expanduser("~/.bun/bin")
        env["PATH"] = f"{node_dir}:{bun_bin}:{path}"
    try:
        subprocess.run(
            ["bash", str(script)],
            env=env,
            timeout=45.0,
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def _open_page_error_needs_session_recreate(message: str) -> bool:
    lowered = message.lower()
    return (
        "no context for session" in lowered
        or "mux_context_disconnected" in lowered
        or "does not own target" in lowered
        or "session with given id not found" in lowered
        or "no target with given id" in lowered
        or "e2e_user_closed_tab" in lowered
    )


def _is_retryable_open_page_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "openpagetransaction wall timeout" in lowered
        or "browser orchestrator response timeout" in lowered
        or "cdp request timeout" in lowered
        or "daemon not running" in lowered
        or "connection reset" in lowered
        or "broken pipe" in lowered
        or "no context for session" in lowered
        or "mux_context_disconnected" in lowered
        or "cdp evaluate failed" in lowered
        or "page.navigate" in lowered
        or "connection refused" in lowered
        or "no such file or directory" in lowered
        or "errno 2" in lowered
        or "operation timeout: navigate" in lowered
        or "operation queue timeout: navigate" in lowered
        or "operation timeout: new_page" in lowered
        or "operation queue timeout: new_page" in lowered
        or "does not own target" in lowered
        or "session with given id not found" in lowered
        or "no target with given id" in lowered
        or "e2e_user_closed_tab" in lowered
    )


def _effective_parallel_load() -> int:
    for key in ("MYRM_E2E_PHASE_C_BURST_LANES", "MYRM_E2E_PARALLEL_ACTIVE_LEASES"):
        raw = os.environ.get(key, "").strip()
        try:
            count = int(raw)
        except ValueError:
            continue
        if count >= 2:
            return count
    return 0


def _parallel_open_page_max_attempts() -> int:
    """R299: cap retries — orchestrator fail-fast wall makes 8×480s storms pointless."""
    try:
        from peer_count_ssot import parallel_active_test_count_ssot

        if parallel_active_test_count_ssot() > 0:
            return 6
    except ImportError:
        pass
    return 3


def _parallel_open_page_timeout_sec(daemon: BrowserOrchestratorClient) -> float:
    from browser_orchestrator_client import (
        orchestrator_open_tx_wall_sec,
        orchestrator_socket_timeout_cap_sec,
    )

    cap = orchestrator_socket_timeout_cap_sec()
    wall = orchestrator_open_tx_wall_sec() + 30.0
    daemon_budget = float(daemon._timeout_sec)
    return min(cap, wall, daemon_budget)


def _recreate_orchestrator_session(
    daemon: BrowserOrchestratorClient,
    session_id: str,
) -> None:
    """Best-effort destroy stale mux context, then create a fresh BrowserContext."""
    try:
        daemon.destroy_session(session_id)
    except (RuntimeError, TimeoutError, OSError):
        pass
    try:
        daemon.create_session(session_id)
    except RuntimeError as create_exc:
        if "already" not in str(create_exc).lower():
            raise
    time.sleep(0.15)


def _open_page_fast_create_with_retry(
    daemon: BrowserOrchestratorClient,
    session_id: str,
    *,
    url: str,
    max_attempts: int | None = None,
) -> dict[str, object]:
    """Single scheduler-op page open for SHARED+READ hot bootstrap (§19.11 TAB-6)."""
    attempts = (
        max_attempts if max_attempts is not None else _parallel_open_page_max_attempts()
    )
    open_timeout_sec = _parallel_open_page_timeout_sec(daemon)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                _recreate_orchestrator_session(daemon, session_id)
            from e2e_orchestrator import touch_wall_progress  # noqa: PLC0415

            touch_wall_progress(current_node="open_page_fast_create")
            target_url = url.strip() or "about:blank"
            # Single RPC: orchestrator createPage runs create+navigate in one daemon
            # transaction — avoids client round-trip window where background blank tabs
            # get E2E_USER_CLOSED_TAB before navigate (§19.11 TAB-6b).
            with daemon.elevated_request_timeout(open_timeout_sec):
                created = daemon.create_page(session_id, url=target_url)
            payload = dict(created)
            return {
                "pageId": int(payload["pageId"]),
                "targetId": str(payload["targetId"]),
                "url": target_url,
            }
        except (TimeoutError, OSError, RuntimeError) as exc:
            last_exc = exc
            message = str(exc)
            if not _is_retryable_open_page_error(message):
                raise
            if _recover_orchestrator_daemon(daemon, message):
                _recreate_orchestrator_session(daemon, session_id)
            elif _open_page_error_needs_session_recreate(message):
                _recreate_orchestrator_session(daemon, session_id)
            if attempt >= attempts:
                break
            time.sleep(min(3.0 * float(attempt), 8.0))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("open_page_fast_create failed without exception")


def _open_page_transaction_with_retry(
    daemon: BrowserOrchestratorClient,
    session_id: str,
    *,
    url: str,
    binding_expression: str | None = None,
    max_attempts: int | None = None,
) -> dict[str, object]:
    """Open page via orchestrator; retry transient CDP/mux stalls under parallel load."""
    attempts = (
        max_attempts if max_attempts is not None else _parallel_open_page_max_attempts()
    )
    open_timeout_sec = _parallel_open_page_timeout_sec(daemon)
    last_exc: BaseException | None = None
    for attempt in range(1, attempts + 1):
        try:
            if attempt > 1:
                _recreate_orchestrator_session(daemon, session_id)
            from e2e_orchestrator import touch_wall_progress  # noqa: PLC0415

            touch_wall_progress(current_node="open_page_transaction")
            with daemon.elevated_request_timeout(open_timeout_sec):
                if binding_expression is not None:
                    created = daemon.open_page_transaction(
                        session_id,
                        url=url,
                        binding_expression=binding_expression,
                    )
                else:
                    created = daemon.open_page_transaction(session_id, url=url)
            return dict(created)
        except (TimeoutError, OSError, RuntimeError) as exc:
            last_exc = exc
            message = str(exc)
            if not _is_retryable_open_page_error(message):
                raise
            if _recover_orchestrator_daemon(daemon, message):
                _recreate_orchestrator_session(daemon, session_id)
            elif _open_page_error_needs_session_recreate(message):
                _recreate_orchestrator_session(daemon, session_id)
            if attempt >= attempts:
                break
            time.sleep(min(3.0 * float(attempt), 8.0))
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("open_page_transaction failed without exception")


def _wait_orchestrator_daemon_ready(
    daemon: BrowserOrchestratorClient,
    *,
    wall_sec: float = 90.0,
) -> None:
    """Wait for daemon; invoke ensure script once after a short unreachable window."""
    deadline = time.monotonic() + wall_sec
    ensure_spawned = False
    while time.monotonic() < deadline:
        if daemon.is_alive():
            return
        elapsed = wall_sec - (deadline - time.monotonic())
        if not ensure_spawned and elapsed >= 8.0:
            _spawn_ensure_orchestrator()
            ensure_spawned = True
        time.sleep(0.5)
    raise RuntimeError(
        "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running — "
        "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
    )


def _apply_orchestrator_shpoib_binding(
    client: OrchestratorChromeClient,
    page: OrchestratorMcpPage,
    url: str,
    *,
    daemon: BrowserOrchestratorClient,
    session_id: str,
) -> None:
    """Seed window.name then navigate so e2e-runtime-bootstrap.js binds private API."""
    api_base = get_open_page_api_url().rstrip("/")
    if not api_base or api_base == "http://127.0.0.1:8080":
        daemon.navigate_page(session_id, page.target_id, url)
        page.url = url
        return
    if not wait_e2e_provider_ready(
        api_url=api_base,
        timeout_sec=e2e_private_api_ready_timeout_sec(60.0),
    ):
        raise RuntimeError(
            f"E2E_RUNTIME_BINDING_FAILED: private API not ready before binding: {api_base}"
        )
    source = e2e_runtime_binding_source()
    if source:
        client.evaluate(
            page,
            f"(() => {{{source} return true; }})()",
            timeout_sec=15.0,
        )
    else:
        client.evaluate(
            page,
            e2e_api_base_inject_js(api_base),
            timeout_sec=15.0,
        )
    daemon.navigate_page(session_id, page.target_id, url)
    page.url = url


@contextmanager
def open_orchestrator_mcp_page(
    url: str,
    *,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[OrchestratorChromeClient, OrchestratorMcpPage]]:
    effective_timeout = request_timeout_sec
    if _effective_parallel_load() >= 2:
        from browser_orchestrator_client import orchestrator_socket_timeout_cap_sec

        effective_timeout = max(
            request_timeout_sec,
            orchestrator_socket_timeout_cap_sec(),
        )
    daemon = BrowserOrchestratorClient(timeout_sec=max(effective_timeout, 90.0))
    wait_wall = float(os.environ.get("MYRM_BROWSER_ORCHESTRATOR_WAIT_SEC", "90"))
    _wait_orchestrator_daemon_ready(daemon, wall_sec=max(20.0, wait_wall))
    session_id = _resolve_session_id()
    if _effective_parallel_load() >= 2:
        _recreate_orchestrator_session(daemon, session_id)
    else:
        daemon.create_session(session_id)
    page = OrchestratorMcpPage(page_id=1, target_id="", url=None)
    client = OrchestratorChromeClient(
        session_id=session_id,
        daemon=daemon,
        request_timeout_sec=effective_timeout,
    )
    try:
        from warm_shell_registry import (  # noqa: PLC0415
            seal_platform_shell,
            set_bootstrap_hot_path,
            shared_read_hot_path_decision,
        )

        hot = shared_read_hot_path_decision(url=url)
        binding_source = e2e_runtime_binding_source()
        pending_binding: str | None = None

        if hot.eligible:
            set_bootstrap_hot_path("fast_create")
            # Hot path skips runtime binding — navigate directly (mirror cold post-bind navigate).
            try:
                created = _open_page_fast_create_with_retry(
                    daemon,
                    session_id,
                    url=url,
                )
            except RuntimeError as hot_exc:
                if not _is_retryable_open_page_error(str(hot_exc)):
                    raise
                set_bootstrap_hot_path("cold")
                _recreate_orchestrator_session(daemon, session_id)
                created = _open_page_transaction_with_retry(
                    daemon,
                    session_id,
                    url=url,
                )
        elif binding_source:
            set_bootstrap_hot_path("cold")
            try:
                created = _open_page_fast_create_with_retry(
                    daemon,
                    session_id,
                    url=url,
                )
                pending_binding = binding_source
            except RuntimeError as bind_exc:
                if not _is_retryable_open_page_error(str(bind_exc)):
                    raise
                binding_expression = (
                    f"(() => {{{binding_source} return true; }})()"
                )
                _recreate_orchestrator_session(daemon, session_id)
                created = _open_page_transaction_with_retry(
                    daemon,
                    session_id,
                    url=url,
                    binding_expression=binding_expression,
                )
        else:
            api_base = get_open_page_api_url().rstrip("/")
            if api_base and api_base != "http://127.0.0.1:8080":
                if not wait_e2e_provider_ready(
                    api_url=api_base,
                    timeout_sec=e2e_private_api_ready_timeout_sec(60.0),
                ):
                    raise RuntimeError(
                        f"E2E_RUNTIME_BINDING_FAILED: private API not ready: {api_base}"
                    )
                inject = e2e_api_base_inject_js(api_base)
                set_bootstrap_hot_path("cold")
                try:
                    created = _open_page_fast_create_with_retry(
                        daemon,
                        session_id,
                        url=url,
                    )
                    pending_binding = inject
                except RuntimeError as inject_exc:
                    if not _is_retryable_open_page_error(str(inject_exc)):
                        raise
                    _recreate_orchestrator_session(daemon, session_id)
                    created = _open_page_transaction_with_retry(
                        daemon,
                        session_id,
                        url=url,
                        binding_expression=f"(() => {{{inject} return true; }})()",
                    )
            else:
                set_bootstrap_hot_path("cold")
                created = _open_page_transaction_with_retry(
                    daemon,
                    session_id,
                    url=url,
                )
        seal_platform_shell(ui_url=url)
        page.page_id = int(created["pageId"])
        page.target_id = str(created["targetId"])
        page.url = str(created.get("url", url))
        client.bind_primary_page(page)
        if pending_binding is not None:
            client.evaluate(
                page,
                f"(() => {{{pending_binding} return true; }})()",
                timeout_sec=min(30.0, effective_timeout),
            )
            target_url = url.strip()
            if target_url and target_url != "about:blank":
                with daemon.elevated_request_timeout(
                    _parallel_open_page_timeout_sec(daemon)
                ):
                    daemon.navigate_page(session_id, page.target_id, target_url)
                page.url = target_url
        try:
            from chrome_e2e.gates.orphan_budget import (
                assert_orphan_budget_invariant,
            )  # noqa: PLC0415

            assert_orphan_budget_invariant()
        except ImportError:
            pass
        yield client, page
    finally:
        daemon.destroy_session(session_id)
