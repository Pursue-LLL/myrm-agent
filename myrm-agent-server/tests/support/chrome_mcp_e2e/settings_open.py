"""Open a settings sub-route, or the wiki settings page, on a page that is ready for it."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

from cdp_chat.support import get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from tests.support.e2e_runtime_guard import heartbeat_once

from .open_page import _ensure_orchestrator_shared_ui_session, open_mcp_page
from .page_guard import _recover_chrome_error_page, dismiss_blocking_modals
from .parallel_load import (
    _bounded_settings_ui_wait_sec,
    _parallel_chrome_e2e_active,
    _settings_heal_reload_timeout_ms,
    _warm_ui_parallel_wait_sec,
)
from .private_api import _ensure_e2e_private_api_live
from .reload import reload_mcp_page
from .settings_wait import (
    _is_settings_route,
    _normalize_settings_url,
    _settings_route_path,
    wait_for_settings_layout,
    wait_for_wiki_settings_shell,
)
from .warm_ui import _settings_http_warm_skippable, _trigger_attach_client_warmup_once, warm_ui_route

_SETTINGS_DISMISSAL_BINDING_JS = """(() => {
  try {
    localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
    sessionStorage.removeItem('e2e_warm_platform_readiness');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE: bool | None = None


def _orchestrator_atomic_route_available() -> bool:
    """True when the live daemon exposes the page/openAppRoute RPC (NAV-2/NAV-3).

    Cached per process — the daemon capability only changes on rebuild/restart.
    """
    global _ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE
    if _ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE is not None:
        return _ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE
    try:
        from browser_orchestrator.client import (  # noqa: PLC0415
            BrowserOrchestratorClient,
        )

        _ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE = BrowserOrchestratorClient().supports_open_app_route()
    except (ImportError, OSError, RuntimeError, TimeoutError):
        _ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE = False
    return _ORCHESTRATOR_ATOMIC_ROUTE_AVAILABLE


@contextmanager
def open_settings_subroute(
    subroute_path: str,
    *,
    timeout_ms: int = 120_000,
    request_timeout_sec: float | None = None,
    warm: bool = True,
    layout_timeout_sec: float = 45.0,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    """SSOT: open /settings shell, navigate to nested subroute, wait settings-layout."""
    touch_wall_progress(current_node="open_settings_subroute")
    if request_timeout_sec is None:
        from browser_orchestrator.client import orchestrator_socket_timeout_cap_sec

        request_timeout_sec = orchestrator_socket_timeout_cap_sec()
    ui_base = get_e2e_ui_url().rstrip("/")
    route_path = _settings_route_path(subroute_path)
    if not route_path.startswith("/settings"):
        raise ValueError(f"open_settings_subroute expects a /settings path, got: {subroute_path!r}")
    shell_url = f"{ui_base}/settings"
    path_only = route_path
    query = ""
    if "?" in subroute_path:
        query = "?" + subroute_path.split("?", 1)[1]
    if path_only == "/settings":
        target_url = shell_url
    else:
        target_url = _normalize_settings_url(f"{ui_base}{path_only}{query}")

    if _parallel_chrome_e2e_active():
        parallel_budget = _warm_ui_parallel_wait_sec(90.0)
        timeout_ms = max(timeout_ms, min(int(parallel_budget * 1000), 180_000))
        request_timeout_sec = max(request_timeout_sec, parallel_budget)
        layout_timeout_sec = max(layout_timeout_sec, _warm_ui_parallel_wait_sec(60.0))

    if warm:
        skip_parallel_http_warm = _parallel_chrome_e2e_active()
        try:
            from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

            skip_parallel_http_warm = skip_parallel_http_warm or parallel_shared_ui_hydrate_queue_enabled()
        except ImportError:
            pass
        if not _settings_http_warm_skippable("/settings") and not skip_parallel_http_warm:
            warm_ui_route(
                "/settings",
                timeout_sec=_warm_ui_parallel_wait_sec(20.0),
            )
        if route_path != "/settings" and not _settings_http_warm_skippable(route_path):
            # §19.11.9 W3c: orchestrator _settings_open_plan atomic navigate — skip nested HTTP warm (85292: 404→heal→510s).
            pass
        _trigger_attach_client_warmup_once(page_url=target_url)

    # Orchestrator absorbs shell reclaim + subroute navigate + hydration
    # atomically via open_app_route (NAV-2/NAV-3) — zero test-layer navigate,
    # zero reload + second-hydrate storm (§19.11.11.2 dead paths deleted).
    touch_wall_progress(current_node="open_settings_subroute_page_open")
    atomic_available = os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1" and _orchestrator_atomic_route_available()
    if atomic_available:
        from browser_orchestrator.e2e import open_app_route_page

        with open_app_route_page(
            target_url,
            request_timeout_sec=request_timeout_sec,
            hydrate_timeout_sec=max(
                45.0,
                (_warm_ui_parallel_wait_sec(layout_timeout_sec) if _parallel_chrome_e2e_active() else layout_timeout_sec),
            ),
            binding_expression=_SETTINGS_DISMISSAL_BINDING_JS,
        ) as (client, page):
            from e2e_session_runtime.lifecycle import complete_bootstrap_phase

            complete_bootstrap_phase(phase_label="owned_settings_page_ready")
            _ensure_orchestrator_shared_ui_session(client, page)
            _ensure_e2e_private_api_live(
                client,
                page,
                timeout_sec=(_warm_ui_parallel_wait_sec(90.0) if _parallel_chrome_e2e_active() else 45.0),
            )
            try:
                dismiss_blocking_modals(client, page, recover_url=target_url)
            except (AssertionError, RuntimeError, TimeoutError, OSError):
                pass
            _recover_chrome_error_page(client, page, target_url=target_url)
            _ensure_e2e_private_api_live(client, page, timeout_sec=45.0)
            heartbeat_once()
            yield client, page  # type: ignore[misc]
        return

    with open_mcp_page(
        target_url,
        timeout_ms=timeout_ms,
        request_timeout_sec=request_timeout_sec,
        skip_settings_layout_wait=True,
    ) as (client, page):
        client.evaluate(
            page,
            _SETTINGS_DISMISSAL_BINDING_JS,
            timeout_sec=15.0,
        )
        _ensure_e2e_private_api_live(
            client,
            page,
            timeout_sec=(_warm_ui_parallel_wait_sec(90.0) if _parallel_chrome_e2e_active() else 45.0),
        )
        reload_mcp_page(
            client,
            page,
            target_url=target_url,
            timeout_ms=_settings_heal_reload_timeout_ms(base_ms=timeout_ms),
        )
        try:
            dismiss_blocking_modals(client, page, recover_url=target_url)
        except (AssertionError, RuntimeError, TimeoutError, OSError):
            pass
        _recover_chrome_error_page(client, page, target_url=target_url)
        if _is_settings_route(target_url):
            wait_for_settings_layout(
                client,
                page,
                page_url=target_url,
                timeout_sec=layout_timeout_sec,
            )
        _ensure_e2e_private_api_live(client, page, timeout_sec=45.0)
        heartbeat_once()
        yield client, page


@contextmanager
def open_wiki_settings_mcp_page(
    wiki_page_url: str,
    *,
    timeout_ms: int = 120_000,
    request_timeout_sec: float = 180.0,
    warm: bool = True,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    """Shell-first navigation for nested /settings/wiki (SettingsSubrouteNavigate SSOT)."""
    from urllib.parse import urlparse

    parsed = urlparse(wiki_page_url)
    subroute = parsed.path or "/settings/wiki"
    if parsed.query:
        subroute = f"{subroute}?{parsed.query}"
    with open_settings_subroute(
        subroute,
        timeout_ms=timeout_ms,
        request_timeout_sec=request_timeout_sec,
        warm=warm,
        layout_timeout_sec=90.0,
    ) as (client, page):
        wait_for_wiki_settings_shell(
            client,
            page,
            page_url=_normalize_settings_url(wiki_page_url),
            timeout_sec=_bounded_settings_ui_wait_sec(45.0),
            require_shell=True,
        )
        yield client, page
