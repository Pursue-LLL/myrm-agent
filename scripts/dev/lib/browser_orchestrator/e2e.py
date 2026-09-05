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
from typing import Iterator, NoReturn

from browser_orchestrator.client import BrowserOrchestratorClient
from cdp_chat.support import (
    e2e_api_base_inject_js,
    e2e_private_api_ready_timeout_sec,
    e2e_page_binding_source,
    e2e_runtime_bootstrap_apply_js,
    get_open_page_api_url,
    wait_e2e_provider_ready,
)

# OrchestratorWatchdog (§24 W3e): daemon ensure is at most once per window.
ORCHESTRATOR_WATCHDOG_SPAWN_COOLDOWN_SEC = 15.0
_orchestrator_watchdog_last_spawn_at: float = 0.0


def _route_binding_expression(extra_expression: str | None) -> str | None:
    """Bind a PRIVATE runtime before the final route can issue API requests."""
    runtime_expression = e2e_runtime_bootstrap_apply_js()
    expressions = [
        expression.strip()
        for expression in (runtime_expression, extra_expression)
        if expression and expression.strip()
    ]
    if not expressions:
        return None
    if len(expressions) == 1:
        return expressions[0]
    runtime_js, extra_js = expressions
    return f"""(async () => {{
  const runtimeResult = await ({runtime_js});
  if (runtimeResult?.ok === false) return runtimeResult;
  const extraResult = await ({extra_js});
  return extraResult ?? runtimeResult;
}})()"""


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

    def _is_orphan_target_error(self, message: str) -> bool:
        lowered = message.lower()
        return (
            "inspected target navigated or closed" in lowered
            or "navigated or closed" in lowered
            or "promise was collected" in lowered
            or self._is_missing_session_context(message)
        )

    def _is_missing_session_context(self, message: str) -> bool:
        lowered = message.lower()
        return (
            "no context for session" in lowered
            or "mux_context_disconnected" in lowered
            or "session with given id not found" in lowered
            or "does not own target" in lowered
            or "no target with given id" in lowered
            or "inspected target navigated or closed" in lowered
            or "navigated or closed" in lowered
        )

    def _ensure_session_context(self) -> None:
        try:
            self._daemon.destroy_session(self._session_id)
        except (RuntimeError, TimeoutError, OSError):
            pass
        try:
            self._daemon.create_session(self._session_id)
        except RuntimeError as exc:
            message = str(exc)
            if "already" in message.lower():
                return
            if _orchestrator_daemon_unreachable(message):
                _recover_orchestrator_daemon(self._daemon, message, wall_sec=45.0)
                self._daemon.create_session(self._session_id)
                return
            raise

    def _reopen_primary_page(
        self, url: str, *, page: OrchestratorMcpPage | None = None
    ) -> OrchestratorMcpPage:
        orphan_timeout_sec = min(45.0, self._request_timeout_sec)
        last_exc: BaseException | None = None
        hot_eligible = False
        try:
            from e2e_core.warm_shell_registry import shared_read_hot_path_decision

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
                const proto =
                  el instanceof HTMLTextAreaElement
                    ? HTMLTextAreaElement.prototype
                    : el instanceof HTMLSelectElement
                      ? HTMLSelectElement.prototype
                      : HTMLInputElement.prototype;
                const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                if (setter) {{
                  setter.call(el, {escaped});
                }} else {{
                  el.value = {escaped};
                }}
                el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                el.dispatchEvent(new Event('change', {{ bubbles: true }}));
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
            or "connection closed before response" in lowered
            or self._is_missing_session_context(message)
        )

    def _operation_result_unknown(self, message: str) -> bool:
        """Return true when an evaluate/navigate request may have executed.

        A response timeout occurs after the daemon has accepted the RPC.  The
        browser may therefore have run JavaScript or started navigation even
        though the client saw no result.  Retrying such a request can duplicate
        user-visible mutations, so the session must be quarantined instead.
        """
        lowered = message.lower()
        if "browser_operation_result_unknown" in lowered:
            return True
        if "daemon not running" in lowered or "connection refused" in lowered:
            return False
        return any(
            marker in lowered
            for marker in (
                "browser orchestrator response timeout",
                "cdp request timeout",
                "connection reset",
                "broken pipe",
                "connection closed before response",
                "connection lost",
                "cdp connection changed during operation",
                "operation timeout: navigate",
                "operation timeout: evaluate",
            )
        )

    def _raise_unknown_operation_result(self, message: str) -> NoReturn:
        """Quarantine the session before exposing an ambiguous operation result."""
        try:
            self._daemon.destroy_session(self._session_id)
        except (TimeoutError, OSError, RuntimeError):
            # The daemon's lease reaper remains the last-resort cleanup owner.
            pass
        raise RuntimeError(
            "BROWSER_OPERATION_RESULT_UNKNOWN: evaluate/navigate request may "
            f"have reached Chrome; session was quarantined; cause={message}"
        )

    def _recover_daemon_if_needed(self, message: str) -> bool:
        return _recover_orchestrator_daemon(self._daemon, message, wall_sec=45.0)

    def evaluate(
        self,
        page: OrchestratorMcpPage,
        expression: str,
        *,
        timeout_sec: float = 15.0,
        await_promise: bool = True,
        intent: str | None = None,
    ) -> object:
        from dev_gate.contract import EvaluateIntent, resolve_evaluate_budget

        effective = min(max(5.0, timeout_sec), self._request_timeout_sec)
        last_exc: BaseException | None = None
        max_attempts = 2 if _effective_parallel_load() >= 2 else 5
        if intent:
            try:
                budget = resolve_evaluate_budget(EvaluateIntent(intent))
                max_attempts = 1 + max(0, budget.mux_max_attempts)
            except ValueError:
                pass
        for attempt in range(1, max_attempts + 1):
            try:
                payload = self._daemon.evaluate_page(
                    self._session_id,
                    page.target_id,
                    expression,
                    timeout_sec=effective,
                    await_promise=await_promise,
                    intent=intent,
                )
                return payload.get("value")
            except (TimeoutError, OSError, RuntimeError) as exc:
                last_exc = exc
                message = str(exc)
                if self._operation_result_unknown(message):
                    self._raise_unknown_operation_result(message)
                if self._recover_daemon_if_needed(message):
                    continue
                if self._is_orphan_target_error(message) and attempt < max_attempts:
                    fallback_url = page.url or "http://127.0.0.1:3000/"
                    try:
                        self._reopen_primary_page(fallback_url, page=page)
                    except (RuntimeError, TimeoutError, OSError) as reopen_exc:
                        if not self._recover_daemon_if_needed(str(reopen_exc)):
                            raise
                    continue
                if self._is_missing_session_context(message):
                    if self._recover_daemon_if_needed(message):
                        fallback_url = page.url or "http://127.0.0.1:3000/"
                        self._reopen_primary_page(fallback_url, page=page)
                        continue
                    self._ensure_session_context()
                    fallback_url = page.url or "http://127.0.0.1:3000/"
                    self._reopen_primary_page(fallback_url, page=page)
                    continue
                if self._is_terminal_tab_error(message) and attempt < max_attempts:
                    fallback = page.url or "http://127.0.0.1:3000/"
                    try:
                        self._reopen_primary_page(fallback, page=page)
                    except (RuntimeError, TimeoutError, OSError):
                        pass
                    continue
                retryable = self._is_retryable_transport_error(message)
                if not retryable or attempt >= max_attempts:
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
                if self._operation_result_unknown(message):
                    self._raise_unknown_operation_result(message)
                if self._recover_daemon_if_needed(message):
                    continue
                if self._is_missing_session_context(message):
                    self._ensure_session_context()
                    continue
                if self._is_terminal_tab_error(message) and attempt < 3:
                    try:
                        from e2e_core.warm_shell_registry import (
                            shared_read_hot_path_decision,
                        )

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
        binding_source = e2e_page_binding_source()
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
    from dev_gate.contract import E2E_ORCHESTRATOR_LEASE_DENIED_TOKEN
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
    return Path(__file__).resolve().parents[5]


def _orchestrator_daemon_unreachable(message: str) -> bool:
    """True when daemon socket is gone or hung under parallel burst (fix#14)."""
    lowered = message.lower()
    if (
        "daemon not running" in lowered
        or "connection refused" in lowered
        or "cdp not connected" in lowered
    ):
        return True
    if "browser orchestrator response timeout" in lowered:
        return (
            _effective_parallel_load() >= 2
            or not BrowserOrchestratorClient(timeout_sec=3.0).is_alive()
        )
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
    """Best-effort daemon (re)start — serialized by ensure script flock.

    OrchestratorWatchdog (§24 W3e): at most one spawn per cooldown window,
    so a Connection-refused storm never triggers a subprocess spawn storm.
    """
    now = time.monotonic()
    global _orchestrator_watchdog_last_spawn_at
    if (
        now - _orchestrator_watchdog_last_spawn_at
        < ORCHESTRATOR_WATCHDOG_SPAWN_COOLDOWN_SEC
    ):
        return
    _orchestrator_watchdog_last_spawn_at = now
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
    if "browser_operation_result_unknown" in lowered:
        return False
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
        or "inspected target navigated or closed" in lowered
        or "navigated or closed" in lowered
        or "e2e_user_closed_tab" in lowered
    )


def _open_page_result_unknown(message: str) -> bool:
    """True when the request may have reached Chrome but its result was lost."""
    lowered = message.lower()
    return any(
        marker in lowered
        for marker in (
            "openpagetransaction wall timeout",
            "browser orchestrator response timeout",
            "cdp request timeout",
            "connection reset",
            "broken pipe",
            "connection closed before response",
            "operation timeout: new_page",
            "operation timeout: navigate",
            "operation timeout: open_app_route",
        )
    )


def _raise_unknown_open_page_result(
    daemon: BrowserOrchestratorClient,
    session_id: str,
    message: str,
) -> NoReturn:
    """Reap the affected session before exposing an ambiguous open-page result."""
    try:
        daemon.destroy_session(session_id)
    except (TimeoutError, OSError, RuntimeError):
        # The daemon's lease reaper remains the owner of last-resort cleanup.
        pass
    raise RuntimeError(
        "BROWSER_OPERATION_RESULT_UNKNOWN: page-open request may have reached "
        f"Chrome; session was quarantined; cause={message}"
    )


def _is_blank_page_url(url: str) -> bool:
    """True for manual-navigation hosts (about:blank/empty) with no app content."""
    stripped = (url or "").strip()
    return not stripped or stripped == "about:blank"


def _effective_parallel_load() -> int:
    for key in ("MYRM_E2E_PHASE_C_BURST_LANES", "MYRM_E2E_PARALLEL_ACTIVE_LEASES"):
        raw = os.environ.get(key, "").strip()
        try:
            count = int(raw)
        except ValueError:
            continue
        if count >= 2:
            return count
    try:
        from e2e_core.peer_count_ssot import parallel_active_test_count_ssot

        return max(0, parallel_active_test_count_ssot())
    except ImportError:
        return 0


def _parallel_open_page_max_attempts() -> int:
    """R299: cap retries — orchestrator fail-fast wall makes multi-minute storms pointless."""
    try:
        from e2e_core.peer_count_ssot import parallel_active_test_count_ssot

        peers = parallel_active_test_count_ssot()
        if peers <= 1:
            return 1
    except ImportError:
        pass
    return 3


def _parallel_open_page_timeout_sec(daemon: BrowserOrchestratorClient) -> float:
    from browser_orchestrator.client import (
        orchestrator_open_tx_wall_sec,
        orchestrator_socket_timeout_cap_sec,
    )

    cap = orchestrator_socket_timeout_cap_sec()
    wall = orchestrator_open_tx_wall_sec() + 30.0
    daemon_budget = float(daemon._timeout_sec)
    return min(cap, wall, daemon_budget)


def _ensure_orchestrator_session(
    daemon: BrowserOrchestratorClient,
    session_id: str,
) -> None:
    """Ensure mux session exists; reuse live BrowserContext (orchestrator session/create SSOT)."""
    try:
        daemon.create_session(session_id)
    except RuntimeError as create_exc:
        if "already" not in str(create_exc).lower():
            raise


def _recreate_orchestrator_session(
    daemon: BrowserOrchestratorClient,
    session_id: str,
) -> None:
    """Best-effort destroy stale mux context, then create a fresh BrowserContext."""
    try:
        daemon.destroy_session(session_id)
    except (RuntimeError, TimeoutError, OSError):
        pass
    _ensure_orchestrator_session(daemon, session_id)
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
            from e2e_core.orchestrator import touch_wall_progress  # noqa: PLC0415

            touch_wall_progress(current_node="open_page_fast_create")
            target_url = url.strip() or "about:blank"
            # Create about:blank first — CDP Target.createTarget+navigate to SPA routes
            # (e.g. /settings) can stall the whole RPC; client navigate after bind is safer.
            with daemon.elevated_request_timeout(open_timeout_sec):
                created = daemon.create_page(session_id, url="about:blank")
            payload = dict(created)
            page_id = int(payload["pageId"])
            target_id = str(payload["targetId"])
            if target_url != "about:blank":
                with daemon.elevated_request_timeout(open_timeout_sec):
                    daemon.navigate_page(session_id, target_id, target_url)
            return {
                "pageId": page_id,
                "targetId": target_id,
                "url": target_url,
            }
        except (TimeoutError, OSError, RuntimeError) as exc:
            last_exc = exc
            message = str(exc)
            if _open_page_result_unknown(message):
                _raise_unknown_open_page_result(daemon, session_id, message)
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
            from e2e_core.orchestrator import touch_wall_progress  # noqa: PLC0415

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
            if _open_page_result_unknown(message):
                _raise_unknown_open_page_result(daemon, session_id, message)
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
    source = e2e_page_binding_source()
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


def _normalize_hot_route(url: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(url.strip())
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    return path or "/"


@dataclass(frozen=True, slots=True)
class SettingsOpenPlan:
    """Orchestrator open plan for nested /settings/* (§19.11 TAB-6b)."""

    reclaim_route: str
    reclaim_url: str
    post_navigate_url: str | None


def _settings_open_plan(url: str) -> SettingsOpenPlan:
    """Shell reclaim at /settings, then CDP navigate to nested subroute when needed."""
    from urllib.parse import urlsplit

    stripped = url.strip()
    parsed = urlsplit(stripped)
    path = parsed.path or "/"
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"

    if parsed.scheme and parsed.netloc:
        origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    else:
        try:
            from cdp_chat.support import get_e2e_ui_url

            origin = get_e2e_ui_url().rstrip("/")
        except ImportError:
            origin = "http://127.0.0.1:3000"

    if path.startswith("/settings/") and path != "/settings":
        return SettingsOpenPlan(
            reclaim_route="/settings",
            reclaim_url=f"{origin}/settings",
            post_navigate_url=stripped,
        )
    return SettingsOpenPlan(
        reclaim_route=path,
        reclaim_url=stripped,
        post_navigate_url=None,
    )


def _parallel_nested_settings_open(
    open_plan: SettingsOpenPlan, parallel_load: int
) -> bool:
    return parallel_load >= 2 and open_plan.post_navigate_url is not None


def _open_parallel_nested_settings_page(
    daemon: BrowserOrchestratorClient,
    session_id: str,
    *,
    url: str,
    burst_preassigned: bool,
) -> dict[str, object]:
    """Parallel nested /settings/* — prefer fast_create; transaction fallback (11455 SSOT)."""
    from e2e_core.warm_shell_registry import set_bootstrap_hot_path  # noqa: PLC0415

    max_attempts = 4 if burst_preassigned else None
    set_bootstrap_hot_path("fast_create")
    try:
        return _open_page_fast_create_with_retry(
            daemon,
            session_id,
            url=url,
            max_attempts=max_attempts,
        )
    except (RuntimeError, TimeoutError, OSError) as fast_exc:
        if not _is_retryable_open_page_error(str(fast_exc)):
            raise
        set_bootstrap_hot_path("transaction")
        _recreate_orchestrator_session(daemon, session_id)
        return _open_page_transaction_with_retry(
            daemon,
            session_id,
            url=url,
            max_attempts=max_attempts,
        )


def _orchestrator_navigate_owned_page(
    daemon: BrowserOrchestratorClient,
    session_id: str,
    page: OrchestratorMcpPage,
    target_url: str,
) -> None:
    nav_timeout_sec = _parallel_open_page_timeout_sec(daemon)
    if _effective_parallel_load() >= 2:
        nav_timeout_sec = min(nav_timeout_sec, 45.0)
    else:
        nav_timeout_sec = max(nav_timeout_sec, 90.0)
    with daemon.bounded_request_timeout(nav_timeout_sec):
        daemon.navigate_page(session_id, page.target_id, target_url)
    page.url = target_url


def _apply_settings_post_navigate(
    daemon: BrowserOrchestratorClient,
    session_id: str,
    page: OrchestratorMcpPage,
    plan: SettingsOpenPlan,
) -> None:
    if plan.post_navigate_url is None:
        return
    _orchestrator_navigate_owned_page(
        daemon,
        session_id,
        page,
        plan.post_navigate_url,
    )


def _resolve_pending_binding(
    binding_source: str | None,
    *,
    needs_binding: bool,
    force_binding: bool = False,
) -> str | None:
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        if binding_source and binding_source.strip():
            return binding_source.strip()
        return None
    if binding_source and binding_source.strip():
        return binding_source.strip()
    if not needs_binding and not force_binding:
        return None
    from cdp_chat.support import (  # noqa: PLC0415
        e2e_page_binding_source,
        e2e_runtime_bootstrap_apply_js,
    )

    bootstrap = e2e_runtime_bootstrap_apply_js()
    if bootstrap and bootstrap.strip():
        return bootstrap.strip()
    retry = e2e_page_binding_source()
    if retry and retry.strip():
        return retry.strip()
    return None


@contextmanager
def open_orchestrator_mcp_page(
    url: str,
    *,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[OrchestratorChromeClient, OrchestratorMcpPage]]:
    from browser_orchestrator.client import orchestrator_socket_timeout_cap_sec

    effective_timeout = request_timeout_sec
    parallel_load = _effective_parallel_load()
    if parallel_load >= 2:
        cap = orchestrator_socket_timeout_cap_sec()
        # Fail-fast under parallel: never grow socket budget with burst queue headroom.
        effective_timeout = min(request_timeout_sec, cap, 60.0)
    daemon = BrowserOrchestratorClient(
        timeout_sec=(
            effective_timeout if parallel_load >= 2 else max(effective_timeout, 90.0)
        )
    )
    wait_wall = float(os.environ.get("MYRM_BROWSER_ORCHESTRATOR_WAIT_SEC", "90"))
    _wait_orchestrator_daemon_ready(daemon, wall_sec=max(20.0, wait_wall))
    session_id = _resolve_session_id()
    _ensure_orchestrator_session(daemon, session_id)
    page = OrchestratorMcpPage(page_id=1, target_id="", url=None)
    client = OrchestratorChromeClient(
        session_id=session_id,
        daemon=daemon,
        request_timeout_sec=effective_timeout,
    )
    try:
        from e2e_core.warm_shell_registry import (  # noqa: PLC0415
            set_bootstrap_hot_path,
            shared_read_hot_path_decision,
        )

        hot = shared_read_hot_path_decision(url=url)
        binding_source = e2e_page_binding_source()
        pending_binding: str | None = None
        force_runtime_binding = (
            parallel_load >= 2 and os.environ.get("E2E_SIGNOFF", "").strip() == "1"
        )
        open_plan = _settings_open_plan(url)
        # Atomic open to nested /settings/* — avoid shell open + separate navigate (82894 45s timeout).
        atomic_open_url = open_plan.post_navigate_url or open_plan.reclaim_url
        open_url = atomic_open_url

        if hot.eligible:
            # A physical page cannot move from the warmup/default BrowserContext
            # into a session's exclusive BrowserContext. Reclaiming it only
            # changed bookkeeping and leaked the borrowed target at teardown.
            # The epoch seal therefore proves shared bundle warmth; every
            # logical session still creates its own page in its own context.
            set_bootstrap_hot_path("fast_create")
            if _parallel_nested_settings_open(open_plan, parallel_load):
                created = _open_parallel_nested_settings_page(
                    daemon,
                    session_id,
                    url=open_url,
                    burst_preassigned=False,
                )
            else:
                try:
                    created = _open_page_fast_create_with_retry(
                        daemon,
                        session_id,
                        url=open_url,
                    )
                except (RuntimeError, TimeoutError, OSError) as hot_exc:
                    if not _is_retryable_open_page_error(str(hot_exc)):
                        raise
                    _recreate_orchestrator_session(daemon, session_id)
                    created = _open_page_fast_create_with_retry(
                        daemon,
                        session_id,
                        url=open_url,
                    )
            if binding_source or hot.needs_binding or force_runtime_binding:
                pending_binding = _resolve_pending_binding(
                    binding_source,
                    needs_binding=hot.needs_binding,
                    force_binding=force_runtime_binding,
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
                binding_expression = f"(() => {{{binding_source} return true; }})()"
                _recreate_orchestrator_session(daemon, session_id)
                created = _open_page_transaction_with_retry(
                    daemon,
                    session_id,
                    url=url,
                    binding_expression=binding_expression,
                )
        else:
            api_base = get_open_page_api_url().rstrip("/")
            parallel_load = _effective_parallel_load()
            burst_preassigned = bool(
                os.environ.get("MYRM_E2E_PREASSIGNED_SEALED_TARGET_ID", "").strip()
            )
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
            elif _parallel_nested_settings_open(open_plan, parallel_load):
                created = _open_parallel_nested_settings_page(
                    daemon,
                    session_id,
                    url=open_url,
                    burst_preassigned=burst_preassigned,
                )
            else:
                set_bootstrap_hot_path("cold")
                try:
                    created = _open_page_fast_create_with_retry(
                        daemon,
                        session_id,
                        url=open_url,
                    )
                except (RuntimeError, TimeoutError, OSError) as cold_exc:
                    if not _is_retryable_open_page_error(str(cold_exc)):
                        raise
                    _recreate_orchestrator_session(daemon, session_id)
                    created = _open_page_transaction_with_retry(
                        daemon,
                        session_id,
                        url=open_url,
                    )
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
        elif open_plan.post_navigate_url is not None:
            created_url = str(page.url or "").strip().rstrip("/")
            target_url = open_plan.post_navigate_url.strip().rstrip("/")
            # Transaction/fast_create may open nested /settings/* atomically — skip redundant navigate (83122).
            if created_url != target_url:
                _apply_settings_post_navigate(daemon, session_id, page, open_plan)
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


@contextmanager
def open_app_route_page(
    url: str,
    *,
    request_timeout_sec: float | None = None,
    hydrate_timeout_sec: float = 60.0,
    binding_expression: str | None = None,
) -> Iterator[tuple[OrchestratorChromeClient, OrchestratorMcpPage]]:
    """SSOT single entry for atomic app-route opens (§19.11.10 NAV-2/NAV-3).

    Delegates the whole isolated create → binding → subroute navigate → hydration
    wait into one Orchestrator ``open_app_route`` transaction (one operation
    credit, progress token). Route/hydration-probe identity comes from the
    RouteManifest — no test-layer navigate or second hydrate wait.

    Blank hosts (``about:blank`` / empty) are manual-navigation pages with no app
    content; they send an empty probe so the daemon skips the hydration wait.

    Must be used for every /settings/* open — new deep-link tests must call this
    (or the tests/support thin wrapper), never client.navigate.
    """
    from e2e_core.route_manifest import (  # noqa: PLC0415
        assert_gate_allowed,
        hydration_probe_js,
        resolve_route_manifest,
    )
    from browser_orchestrator.client import (  # noqa: PLC0415
        orchestrator_socket_timeout_cap_sec,
    )
    from cdp_chat.support import get_e2e_ui_url  # noqa: PLC0415

    manifest = resolve_route_manifest(url)
    # Blank pages (about:blank / empty) are manual-navigation hosts with no app
    # content to hydrate; the daemon skips the hydration wait when the probe is
    # empty (§19.11.10 NAV-3). Only real app routes resolve a probe + gate check.
    if _is_blank_page_url(url):
        probe_js = ""
    else:
        probe_js = hydration_probe_js(manifest.hydration_gate)
        assert_gate_allowed(manifest.hydration_gate, url)

    parallel_load = _effective_parallel_load()
    ssot_cap = orchestrator_socket_timeout_cap_sec()
    resolved_request = (
        request_timeout_sec if request_timeout_sec is not None else ssot_cap
    )
    # R299-SSOT: under parallel load the client must not abandon before the daemon
    # queue budget (open_app_route queue wait ≤ DEV_OPEN_PAGE_TRANSACTION_WALL_SEC).
    if parallel_load >= 2:
        effective_timeout = max(resolved_request, ssot_cap)
    else:
        effective_timeout = resolved_request
    daemon = BrowserOrchestratorClient(timeout_sec=effective_timeout)
    wait_wall = float(os.environ.get("MYRM_BROWSER_ORCHESTRATOR_WAIT_SEC", "90"))
    _wait_orchestrator_daemon_ready(daemon, wall_sec=max(20.0, wait_wall))
    if not daemon.supports_open_app_route():
        raise RuntimeError(
            "BROWSER_ORCHESTRATOR_CAPABILITY_MISSING: page/openAppRoute is required"
        )
    session_id = _resolve_session_id()
    _ensure_orchestrator_session(daemon, session_id)
    page = OrchestratorMcpPage(page_id=1, target_id="", url=None)
    client = OrchestratorChromeClient(
        session_id=session_id,
        daemon=daemon,
        request_timeout_sec=effective_timeout,
    )
    try:
        route_binding_expression = _route_binding_expression(binding_expression)
        result = daemon.open_app_route(
            session_id,
            url=url,
            shell_path=f"{get_e2e_ui_url().rstrip('/')}{manifest.shell_path}",
            hydration_probe=probe_js,
            hydrate_timeout_sec=hydrate_timeout_sec,
            binding_expression=route_binding_expression,
        )
        page.page_id = int(result["pageId"])
        page.target_id = str(result["targetId"])
        page.url = str(result.get("url", url))
        client.bind_primary_page(page)
        if os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper() == "SHARED":
            from cdp_chat.support import get_open_page_api_url  # noqa: PLC0415
            from e2e_core.warm_shell_registry import (
                seal_platform_shell,
            )  # noqa: PLC0415

            if get_open_page_api_url().rstrip("/") == "http://127.0.0.1:8080":
                seal_platform_shell(
                    ui_url=url,
                    route_path=manifest.shell_path,
                )
        from e2e_core.orchestrator import touch_wall_progress  # noqa: PLC0415

        touch_wall_progress(current_node="open_app_route")
        yield client, page
    finally:
        daemon.destroy_session(session_id)
