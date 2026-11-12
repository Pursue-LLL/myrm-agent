"""Open a page through the browser orchestrator: open_mcp_page, its async form and the shared-UI session."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass

from cdp_chat.support import e2e_api_base_inject_js, get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from dev_gate.contract import EvaluateIntent, is_e2e_signoff_runtime, resolve_evaluate_budget
from e2e_core.orchestrator import touch_wall_progress

from .bridge import _ensure_react_e2e_bridge_timeout_sec, _orchestrator_shared_ui_contract_timeout_sec, wait_for_react_e2e_bridge
from .parallel_load import _bounded_settings_ui_wait_sec
from .settings_wait import _SETTINGS_LAYOUT_READY_JS, _is_blank_page_url, _is_settings_route, wait_for_settings_layout

_APP_LAYOUT_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="app-layout"]'),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'app',
}))()"""


_MCP_SETTINGS_PAGE_READY_JS = """(() => ({
  ready: /MCP 服务配置|MCP Service/i.test(document.body?.innerText || ''),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'mcp-settings',
}))()"""


def _page_shell_ready_js_for_url(url: str) -> str:
    """Settings routes use SettingsLayout, not AppLayout — do not wait for app-layout there."""
    from urllib.parse import urlparse

    path = urlparse(url).path
    if path.startswith("/settings/mcp"):
        return _MCP_SETTINGS_PAGE_READY_JS
    if path.startswith("/settings"):
        return _SETTINGS_LAYOUT_READY_JS
    return _APP_LAYOUT_READY_JS


def _require_orchestrator_for_formal_e2e() -> None:
    lane = os.environ.get("MYRM_E2E_LANE", "").strip()
    if not lane:
        return
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        return
    from dev_gate.contract import BROWSER_ORCHESTRATOR_REQUIRED_TOKEN  # noqa: PLC0415

    raise RuntimeError(
        f"{BROWSER_ORCHESTRATOR_REQUIRED_TOKEN}: formal chrome_e2e requires "
        "MYRM_BROWSER_ORCHESTRATOR=1 — launch via ./myrm-dev test, not raw pytest/mux"
    )


@dataclass(slots=True)
class _OrchestratorSharedUiChat:
    """Adapter so orchestrator MCP pages run apply_shared_ui_session_contract."""

    client: ChromeMcpClient
    page: McpPage
    _runtime_bootstrapped: bool = False

    async def evaluate(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        recv_timeout: float = 30.0,
        intent: EvaluateIntent | None = None,
    ) -> object:
        if intent is not None:
            budget = resolve_evaluate_budget(intent)
            await_promise = budget.await_promise
            recv_timeout = budget.cdp_timeout_sec
        timeout = max(5.0, recv_timeout)
        expr = expression
        if await_promise and "async" not in expression[:48]:
            expr = f"(async () => {{ return await ({expression}); }})()"
        return await asyncio.to_thread(
            self.client.evaluate,
            self.page,
            expr,
            timeout_sec=timeout,
            await_promise=await_promise,
            intent=intent.value if intent is not None else None,
        )

    async def ensure_e2e_api_base_binding(self) -> None:
        from cdp_chat.support import e2e_runtime_bootstrap_apply_js

        inject = e2e_api_base_inject_js()
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if bootstrap_js is not None and not self._runtime_bootstrapped:
            result = await self.evaluate(
                bootstrap_js,
                intent=EvaluateIntent.AGENT_SUBMIT,
            )
            if isinstance(result, dict) and result.get("ok") is True:
                self._runtime_bootstrapped = True
                return
        probe = await self.evaluate(inject, intent=EvaluateIntent.ROUTE_ATTACH)
        if isinstance(probe, dict) and probe.get("ok") is False:
            raise RuntimeError(f"E2E API base inject failed: {probe.get('err', probe)}")

    async def ensure_react_e2e_bridge(self, *, timeout_sec: float = 90.0) -> None:
        resolved_timeout = _ensure_react_e2e_bridge_timeout_sec(timeout_sec)
        await asyncio.to_thread(
            wait_for_react_e2e_bridge,
            self.client,
            self.page,
            timeout_sec=resolved_timeout,
            page_url=getattr(self.page, "url", None) or get_e2e_ui_url(),
            require_attach=True,
        )


def _run_in_isolated_thread_loop(func: Callable[[], None]) -> None:
    """Execute target func in a clean dedicated thread without inheriting parent thread async state."""
    errors: list[BaseException] = []

    def _target() -> None:
        try:
            func()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=_target, daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]


def _ensure_orchestrator_shared_ui_session(
    client: ChromeMcpClient,
    page: McpPage,
) -> None:
    """Orchestrator open_page skips cdp_chat bootstrap — run UI session contract here."""
    from e2e_core.shared_ui_session import (
        current_search_policy,
        maybe_apply_shared_ui_session_contract,
    )

    if current_search_policy() is None:
        return
    chat = _OrchestratorSharedUiChat(client=client, page=page)
    last_exc: BaseException | None = None
    for attempt in range(2):
        try:
            # Run in worker thread with clean event loop to prevent RuntimeError / CancelledError
            def _runner() -> None:
                asyncio.run(
                    maybe_apply_shared_ui_session_contract(
                        chat,
                        timeout_sec=_orchestrator_shared_ui_contract_timeout_sec(),
                    )
                )

            _run_in_isolated_thread_loop(_runner)
            return
        except RuntimeError as exc:
            last_exc = exc
            err_text = str(exc)
            if attempt >= 1 or "navigated or closed" not in err_text.lower():
                raise
            touch_wall_progress(current_node="orchestrator_ui_session_retry")
            time.sleep(2.0)
            wait_for_react_e2e_bridge(
                client,
                page,
                timeout_sec=90.0,
                page_url=getattr(page, "url", None) or get_e2e_ui_url(),
                require_attach=True,
            )
    if last_exc is not None:
        raise last_exc


@contextmanager
def open_mcp_page(
    url: str,
    *,
    timeout_ms: int | None = None,
    request_timeout_sec: float = 180.0,
    skip_settings_layout_wait: bool = False,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    _require_orchestrator_for_formal_e2e()
    resolved_timeout_ms = timeout_ms if timeout_ms is not None else 90_000
    if is_e2e_signoff_runtime():
        resolved_timeout_ms = min(resolved_timeout_ms, 90_000)
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        from browser_orchestrator.e2e import open_app_route_page
        from e2e_session_runtime.lifecycle import complete_bootstrap_phase

        with open_app_route_page(
            url,
            request_timeout_sec=request_timeout_sec,
            hydrate_timeout_sec=_bounded_settings_ui_wait_sec(45.0),
        ) as (client, page):
            complete_bootstrap_phase(phase_label="owned_page_ready")
            if not _is_blank_page_url(url):
                # Blank hosts carry no app content; the shared-UI bridge contract
                # only applies to real app routes.
                _ensure_orchestrator_shared_ui_session(client, page)
            if _is_settings_route(url) and not skip_settings_layout_wait:
                wait_for_settings_layout(
                    client,
                    page,
                    page_url=url,
                    timeout_sec=_bounded_settings_ui_wait_sec(45.0),
                )
            yield client, page  # type: ignore[misc]
        return
    from dev_gate.contract import BROWSER_ORCHESTRATOR_REQUIRED_TOKEN

    raise RuntimeError(
        f"{BROWSER_ORCHESTRATOR_REQUIRED_TOKEN}: Dev Gate chrome_e2e requires "
        "MYRM_BROWSER_ORCHESTRATOR=1 — launch via ./myrm-dev test -m chrome_e2e"
    )


@dataclass(slots=True)
class OpenMcpPageSession:
    """Async handle for ``open_mcp_page`` — caller must ``await aclose()`` (Phase3-D)."""

    _cm: AbstractContextManager[tuple[ChromeMcpClient, McpPage]]
    client: ChromeMcpClient
    page: McpPage

    async def aclose(self) -> None:
        await asyncio.to_thread(self._cm.__exit__, None, None, None)


async def open_mcp_page_async(
    url: str,
    *,
    timeout_ms: int | None = None,
    request_timeout_sec: float = 180.0,
) -> OpenMcpPageSession:
    """Open owned MCP page via TPMc SSOT without blocking the asyncio event loop."""

    def _open_sync() -> OpenMcpPageSession:
        cm = open_mcp_page(
            url,
            timeout_ms=timeout_ms,
            request_timeout_sec=request_timeout_sec,
        )
        client, page = cm.__enter__()
        return OpenMcpPageSession(_cm=cm, client=client, page=page)

    return await asyncio.to_thread(_open_sync)
