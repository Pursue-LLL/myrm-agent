"""Keep an E2E page usable: desktop viewport, offscreen window restore, blocking modals, chrome-error pages and a settings page stuck on its loading shell."""

from __future__ import annotations

import json
import os
import time
import urllib.request

from cdp_chat.support import DISMISS_MODALS_JS, get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage

from .parallel_load import _parallel_chrome_e2e_active, _settings_heal_reload_timeout_ms, _warm_ui_parallel_wait_sec
from .probe_result import _coerce_evaluate_result
from .reload import reload_mcp_page
from .warm_ui import _trigger_attach_client_warmup_once, _trigger_attach_frontend_heal_once, warm_ui_route

_ENSURE_DESKTOP_VIEWPORT_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore — some profiles block resizeTo
  }
  return { width: window.innerWidth, height: window.innerHeight };
})()"""


def ensure_desktop_viewport(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    raw = client.evaluate(page, _ENSURE_DESKTOP_VIEWPORT_JS, timeout_sec=5.0)
    return raw if isinstance(raw, dict) else {"value": raw}


_LOCALHOST_PAGE_JS = """(() => {
  const host = location.hostname;
  return {
    ready: host === '127.0.0.1' || host === 'localhost',
    href: location.href,
  };
})()"""


def dismiss_blocking_modals(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    recover_url: str | None = None,
) -> None:
    """Dismiss onboarding/migration overlays that block E2E clicks (SSOT: cdp_chat.support)."""
    page_url = getattr(page, "url", None)
    target_url = recover_url or (page_url if isinstance(page_url, str) and page_url.strip() else None)
    if not target_url:
        target_url = f"{get_e2e_ui_url().rstrip('/')}/"
    last: dict[str, object] = {}
    max_attempts = 2 if _parallel_chrome_e2e_active() else 5
    for attempt in range(max_attempts):
        raw = client.evaluate(page, _LOCALHOST_PAGE_JS, timeout_sec=15.0)
        last = _coerce_evaluate_result(raw)
        href = str(last.get("href", ""))
        if last.get("ready") is True and "chrome-error://" not in href:
            break
        if attempt >= max_attempts - 1 or not isinstance(target_url, str) or not target_url.strip():
            raise AssertionError(f"Page not on localhost after chrome-error recovery: {last}")
        if "chrome-error://" in href:
            _trigger_attach_frontend_heal_once()
            try:
                from e2e_core.endpoint_health import classify_ui_endpoint_error

                ui_probe_error = classify_ui_endpoint_error(
                    get_e2e_ui_url(),
                    timeout_sec=5.0,
                )
                if ui_probe_error is None:
                    warm_ui_route("/settings", timeout_sec=30.0)
            except (ImportError, RuntimeError, OSError, TimeoutError):
                pass
        reload_mcp_page(client, page, target_url=target_url, timeout_ms=120_000)
    dismissed = client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
    assert isinstance(dismissed, dict) and dismissed.get("ok") is True, dismissed


def _recover_chrome_error_page(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    target_url: str,
) -> None:
    """Heal shared FE + reload when CDP tab landed on chrome-error:// under parallel burst."""
    raw = client.evaluate(page, _LOCALHOST_PAGE_JS, timeout_sec=10.0)
    last = _coerce_evaluate_result(raw)
    href = str(last.get("href", ""))
    if last.get("ready") is True and "chrome-error://" not in href:
        return
    _trigger_attach_frontend_heal_once()
    try:
        from e2e_core.endpoint_health import classify_ui_endpoint_error

        if classify_ui_endpoint_error(get_e2e_ui_url(), timeout_sec=8.0) is not None:
            warm_ui_route("/settings", timeout_sec=_warm_ui_parallel_wait_sec(25.0))
    except (ImportError, RuntimeError, OSError, TimeoutError):
        warm_ui_route("/settings", timeout_sec=_warm_ui_parallel_wait_sec(25.0))
    reload_mcp_page(
        client,
        page,
        target_url=target_url,
        timeout_ms=_settings_heal_reload_timeout_ms(),
    )
    dismiss_blocking_modals(client, page, recover_url=target_url)


def _settings_layout_visible(client: ChromeMcpClient, page: McpPage) -> bool:
    raw = client.evaluate(
        page,
        "!!document.querySelector('[data-testid=\"settings-layout\"]')",
        timeout_sec=15.0,
    )
    return raw is True


def _heal_settings_deferred_loading(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    page_url: str,
) -> None:
    """Reload + client warmup when SettingsLayout stuck on settings-deferred-loading."""
    if _settings_layout_visible(client, page):
        return
    body_empty = False
    try:
        raw_len = client.evaluate(
            page,
            "document.body?.innerText?.length ?? 0",
            timeout_sec=10.0,
        )
        body_empty = int(raw_len or 0) == 0
    except (RuntimeError, TimeoutError, OSError, TypeError, ValueError):
        body_empty = True
    if not _parallel_chrome_e2e_active() or body_empty:
        _trigger_attach_frontend_heal_once()
    _trigger_attach_client_warmup_once(page_url=page_url)
    reload_mcp_page(
        client,
        page,
        target_url=page_url,
        timeout_ms=_settings_heal_reload_timeout_ms(),
    )
    if _parallel_chrome_e2e_active():
        return
    try:
        dismiss_blocking_modals(client, page, recover_url=page_url)
    except (AssertionError, RuntimeError, TimeoutError, OSError):
        pass


_WINDOW_RESTORE_LAST_TS: dict[str, float] = {}
_WINDOW_RESTORE_COOLDOWN_SEC = 8.0


def _restore_e2e_window_via_cdp(page: object) -> bool:
    """Restore render focus and re-park the owning window via direct CDP.

    Window policy is OFFSCREEN-NORMAL: the orchestrator parks every background
    tab at an offscreen normal position (never minimized) so Chrome keeps
    running requestAnimationFrame. E2E Chrome is launched with Playwright
    render flags (--disable-backgrounding-occluded-windows / --disable-renderer-
    backgrounding / --disable-background-timer-throttling), so an occluded /
    non-frontmost window keeps rendering without any activation (§26.21) — this
    helper is now a REGRESSION FALLBACK only. It is invoked solely when a probe
    reports ``__windowHidden`` (document.visibilityState === 'hidden'), which
    happens only if the window policy regresses (e.g. someone reintroduces
    minimized). Cooldown-guarded; direct CDP via the E2E Chrome port — no
    orchestrator RPC change needed.
    """
    target_id = str(getattr(page, "target_id", "") or "")
    if not target_id:
        return False
    now = time.monotonic()
    if now - _WINDOW_RESTORE_LAST_TS.get(target_id, 0.0) < _WINDOW_RESTORE_COOLDOWN_SEC:
        return False
    port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as resp:
            browser_ws = str(json.load(resp)["webSocketDebuggerUrl"])
    except (OSError, TimeoutError, ValueError, KeyError):
        return False
    try:
        from websockets.sync.client import connect as _ws_connect
    except ImportError:
        return False
    try:
        with _ws_connect(browser_ws, open_timeout=10, close_timeout=5) as ws:
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Browser.getWindowForTarget",
                        "params": {"targetId": target_id},
                    }
                )
            )
            while True:
                msg = json.loads(ws.recv(timeout=15))
                if msg.get("id") == 1:
                    break
            window_id = msg.get("result", {}).get("windowId")
            if not window_id:
                return False
            ws.send(
                json.dumps(
                    {
                        "id": 2,
                        "method": "Browser.setWindowBounds",
                        "params": {
                            "windowId": window_id,
                            "bounds": {
                                "windowState": "normal",
                                "left": -24000,
                                "top": -24000,
                                "width": 1400,
                                "height": 900,
                            },
                        },
                    }
                )
            )
            while True:
                msg2 = json.loads(ws.recv(timeout=15))
                if msg2.get("id") == 2:
                    break
    except (OSError, TimeoutError, ValueError):
        return False
    # Focus emulation restores the renderer signal without changing macOS window
    # ordering. Page.bringToFront/Target.activateTarget are forbidden because the
    # E2E Chrome process shares the user's Chrome app bundle and steals focus.
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as resp:
            targets = json.load(resp)
        target_ws = next(
            (t.get("webSocketDebuggerUrl") for t in targets if t.get("id") == target_id),
            None,
        )
        if not target_ws:
            return False
        with _ws_connect(target_ws, open_timeout=10, close_timeout=5) as ws:
            ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "method": "Emulation.setFocusEmulationEnabled",
                        "params": {"enabled": True},
                    }
                )
            )
            while True:
                msg = json.loads(ws.recv(timeout=15))
                if msg.get("id") == 1:
                    break
    except (OSError, TimeoutError, ValueError):
        return False
    _WINDOW_RESTORE_LAST_TS[target_id] = time.monotonic()
    return True
