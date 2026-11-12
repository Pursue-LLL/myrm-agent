"""Wait for the settings shell, the agent settings editor and the wiki settings shell; settings URL helpers."""

from __future__ import annotations

import ast

from cdp_chat.support import e2e_runtime_binding, get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from .page_guard import _heal_settings_deferred_loading, dismiss_blocking_modals
from .parallel_load import _bounded_settings_ui_wait_sec, _parallel_chrome_e2e_active
from .private_api import _ensure_e2e_private_api_live
from .reload import reload_mcp_page
from .wait_state import wait_for_state
from .warm_ui import _trigger_attach_client_warmup_once

_AGENT_SETTINGS_EDITOR_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="agent-tab-capabilities"]'),
  hasAppLayout: !!document.querySelector('[data-testid="app-layout"]'),
  hasDeferredLoading: !!document.querySelector('[data-testid="settings-deferred-loading"]'),
  apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
  runtimeId: window.__MYRM_E2E_RUNTIME__?.runtimeId ?? null,
  bodyLength: (document.body?.innerText || '').length,
  pathname: location.pathname,
  url: location.href,
}))()"""

_WIKI_SETTINGS_SHELL_READY_JS = """(() => {
  const bodyText = document.body?.innerText || '';
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  const dedupTab = document.querySelector('[data-testid="wiki-dedup-tab"]');
  const layout = document.querySelector('[data-testid="app-layout"]');
  const settingsLayout = document.querySelector('[data-testid="settings-layout"]');
  const deferredLoading = document.querySelector('[data-testid="settings-deferred-loading"]');
  const pathname = location.pathname.replace(/\\/+$/, '');
  return {
    ready:
      pathname.endsWith('/settings/wiki') &&
      !!layout &&
      !deferredLoading &&
      (!!shell || !!dedupTab),
    pathname: location.pathname,
    bodyLength: bodyText.length,
    hasShell: !!shell,
    hasDedupTab: !!dedupTab,
    hasAppLayout: !!layout,
    hasSettingsLayout: !!settingsLayout,
    hasDeferredLoading: !!deferredLoading,
  };
})()"""


def wait_for_agent_settings_editor(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    page_url: str,
    timeout_sec: float = 120.0,
) -> dict[str, object]:
    """Wait for Agent settings editor tabs after SHPOIB private API binding is live."""
    editor_ready: dict[str, object] = {}
    per_attempt_sec = min(90.0, max(35.0, timeout_sec / 3.0))
    _trigger_attach_client_warmup_once(page_url=page_url)

    for attempt in range(3):
        _ensure_e2e_private_api_live(
            client,
            page,
            timeout_sec=min(45.0, max(15.0, per_attempt_sec / 2)),
        )
        dismiss_blocking_modals(client, page, recover_url=page_url)
        if _is_settings_route(page_url):
            try:
                wait_for_settings_layout(
                    client,
                    page,
                    page_url=page_url,
                    timeout_sec=min(45.0, per_attempt_sec),
                )
            except AssertionError:
                if attempt >= 2:
                    raise

        try:
            editor_ready = wait_for_state(
                client,
                page,
                _AGENT_SETTINGS_EDITOR_READY_JS,
                timeout_sec=per_attempt_sec,
                page_url=page_url,
                blank_heal_mode="direct",
            )
            if editor_ready.get("ready") is True:
                return editor_ready
            if editor_ready.get("apiBase") is None and e2e_runtime_binding() is not None and attempt < 2:
                reload_mcp_page(client, page, target_url=page_url, timeout_ms=120_000)
                dismiss_blocking_modals(client, page, recover_url=page_url)
                continue
        except AssertionError:
            if attempt >= 2:
                raise
        if attempt < 2:
            _trigger_attach_client_warmup_once(page_url=page_url)
            reload_mcp_page(client, page, target_url=page_url, timeout_ms=120_000)
            dismiss_blocking_modals(client, page, recover_url=page_url)

    raise AssertionError(f"Agent settings editor did not become ready: {editor_ready}")


def wait_for_wiki_settings_shell(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    page_url: str,
    timeout_sec: float = 45.0,
    require_shell: bool = False,
) -> dict[str, object]:
    """Wait for Settings Wiki dynamic section after warm route / open_mcp_page."""
    wiki_ready: dict[str, object] = {}
    bounded = _bounded_settings_ui_wait_sec(timeout_sec)
    parallel = _parallel_chrome_e2e_active()
    # Settings routes: direct reload + deferred heal SSOT. chat_bridge navigates
    # home+back (90s+60s+90s per pass) and burns pytest budget under parallel.
    heal_mode = "direct"
    attempts = 1 if parallel else 2

    for attempt in range(attempts):
        try:
            wiki_ready = wait_for_state(
                client,
                page,
                _WIKI_SETTINGS_SHELL_READY_JS,
                timeout_sec=bounded,
                page_url=page_url,
                blank_heal_mode=heal_mode,
            )
            if wiki_ready.get("ready") is True and (not require_shell or wiki_ready.get("hasShell") is True):
                return wiki_ready
        except AssertionError:
            if attempt >= attempts - 1:
                raise
        if attempt < attempts - 1 and not parallel:
            reload_mcp_page(client, page, target_url=page_url, timeout_ms=90_000)
            try:
                dismiss_blocking_modals(client, page, recover_url=page_url)
            except (AssertionError, RuntimeError, TimeoutError, OSError):
                pass

    raise AssertionError(f"Wiki settings shell did not become ready: {wiki_ready}")


def _settings_route_path(url_or_path: str) -> str:
    from urllib.parse import urlparse

    raw = url_or_path.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        path = urlparse(raw).path or "/"
    else:
        path = raw.split("?", 1)[0].split("#", 1)[0]
        path = path if path.startswith("/") else f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/") or "/"
    return path


def _is_settings_route(url_or_path: str) -> bool:
    return _settings_route_path(url_or_path).startswith("/settings")


def _normalize_settings_url(url_or_path: str) -> str:
    from urllib.parse import urlparse

    raw = url_or_path.strip()
    if raw.startswith("http://") or raw.startswith("https://"):
        parsed = urlparse(raw)
        path = parsed.path or "/"
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")
        query = f"?{parsed.query}" if parsed.query else ""
        return f"{parsed.scheme}://{parsed.netloc}{path}{query}"
    path = raw.split("?", 1)[0].split("#", 1)[0]
    path = path if path.startswith("/") else f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query = f"?{raw.split('?', 1)[1]}" if "?" in raw else ""
    return f"{path}{query}"


def _is_blank_page_url(url_or_path: str) -> bool:
    """True for manual-navigation hosts (about:blank/empty) with no app content."""
    stripped = (url_or_path or "").strip()
    return not stripped or stripped == "about:blank"


def wait_for_settings_layout(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    page_url: str | None = None,
    timeout_sec: float = 45.0,
) -> dict[str, object]:
    """Wait for SettingsLayout hydration — never use chat bridge on /settings/*."""
    if not page_url:
        page_url = f"{get_e2e_ui_url().rstrip('/')}/settings"
    else:
        page_url = _normalize_settings_url(page_url)
    bounded = _bounded_settings_ui_wait_sec(timeout_sec)
    layout_ready: dict[str, object] = {}
    max_attempts = 2 if _parallel_chrome_e2e_active() else 3
    for attempt in range(max_attempts):
        touch_wall_progress(current_node="wait_for_settings_layout")
        if attempt == 0:
            _trigger_attach_client_warmup_once(page_url=page_url)
        try:
            layout_ready = wait_for_state(
                client,
                page,
                _SETTINGS_LAYOUT_READY_JS,
                timeout_sec=bounded,
                page_url=page_url,
                blank_heal_mode="direct",
            )
            if layout_ready.get("ready") is True:
                return layout_ready
        except (AssertionError, RuntimeError) as exc:
            err_text = str(exc)
            marker = "did not become ready:"
            if marker in err_text:
                tail = err_text.split(marker, 1)[1].strip()
                try:
                    parsed = ast.literal_eval(tail)
                    if isinstance(parsed, dict):
                        layout_ready = parsed
                except (ValueError, SyntaxError):
                    layout_ready = {"ready": False, "err": err_text}
            elif not layout_ready:
                layout_ready = {"ready": False, "err": err_text}
        if attempt < max_attempts - 1:
            _heal_settings_deferred_loading(client, page, page_url=page_url)
    err_text = str(layout_ready.get("err", ""))
    if "chrome-error" in err_text:
        raise RuntimeError(f"chrome-error: Settings layout did not become ready: {layout_ready}")
    raise AssertionError(f"Settings layout did not become ready: {layout_ready}")


_SETTINGS_LAYOUT_READY_JS = """(() => ({
  ready:
    location.pathname.startsWith('/settings') &&
    (
      !!document.querySelector('[data-testid="settings-layout"]') ||
      (
        !!document.querySelector('aside') &&
        !!document.querySelector('[data-section][data-active]') &&
        (document.body?.innerText?.length ?? 0) > 40
      )
    ),
  deferredLoading:
    !!document.querySelector('[data-testid="settings-deferred-loading"]') ||
    !!document.querySelector('[data-testid="settings-route-loading"]'),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'settings',
}))()"""
