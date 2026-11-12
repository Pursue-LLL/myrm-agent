"""Poll an in-page predicate until it reports ready, healing blank, errored or modal-covered pages on the way."""

from __future__ import annotations

import time

from cdp_chat.support import get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from .bridge import wait_for_react_e2e_bridge
from .page_guard import _heal_settings_deferred_loading, _restore_e2e_window_via_cdp, dismiss_blocking_modals
from .parallel_load import _parallel_chrome_e2e_active, _settings_heal_reload_timeout_ms
from .probe_result import _coerce_evaluate_result, _looks_like_cdp_transport_error, _state_looks_blank
from .reload import reload_mcp_page
from .warm_ui import _trigger_attach_client_warmup_once


def wait_for_state(
    client: ChromeMcpClient,
    page: McpPage,
    expression: str,
    *,
    timeout_sec: float = 45.0,
    page_url: str | None = None,
    blank_heal_mode: str = "chat_bridge",
    pin_direct_blank_heal: bool = False,
) -> dict[str, object]:
    settings_route = bool(page_url and "/settings" in page_url)
    if settings_route:
        blank_heal_mode = "direct"
    elif not pin_direct_blank_heal and _parallel_chrome_e2e_active() and blank_heal_mode == "direct" and not settings_route:
        blank_heal_mode = "chat_bridge"
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    last_touch = 0.0
    polls = 0
    reload_passes = 0
    parallel_active = _parallel_chrome_e2e_active()
    max_reload_passes = (
        3
        if pin_direct_blank_heal
        else (1 if settings_route and parallel_active else (3 if settings_route else (1 if parallel_active else 3)))
    )
    transport_streak = 0
    dom_hidden = False
    ui_home = f"{get_e2e_ui_url().rstrip('/')}/"
    eval_cap = 25.0 if parallel_active else 60.0
    reload_timeout_ms = _settings_heal_reload_timeout_ms()

    while time.monotonic() < deadline:
        polls += 1
        remaining = max(0.0, deadline - time.monotonic())
        now = time.monotonic()
        if now - last_touch >= 5.0:
            touch_wall_progress(current_node="wait_for_state")
            last_touch = now
        try:
            raw = client.evaluate(
                page,
                expression,
                timeout_sec=max(5.0, min(eval_cap, remaining)),
            )
        except (RuntimeError, TimeoutError, OSError) as exc:
            err_text = str(exc)
            last = {"ready": False, "err": err_text}
            if _looks_like_cdp_transport_error(err_text):
                transport_streak += 1
                if transport_streak >= 3:
                    raise RuntimeError(err_text) from exc
            else:
                transport_streak = 0
            time.sleep(0.25)
            continue
        transport_streak = 0
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return last
        window_hidden = bool(last.get("__windowHidden"))
        body_probe = int(last.get("bodyLength") or last.get("bodyLen") or 0)
        if (
            last.get("ready") is not True
            and not dom_hidden
            and (window_hidden or body_probe > 0)
            and _restore_e2e_window_via_cdp(page)
        ):
            # Window went hidden (offscreen policy regression or external
            # minimize) — Chrome pauses rendering and the UI freezes on its SSR
            # skeleton. Restore the window and re-evaluate instead of failing on
            # a frozen skeleton.
            continue
        if body_probe == 0 and not dom_hidden:
            # innerText reads '' while the window is offscreen-hidden (AOS agent
            # surface) even when the DOM is fully rendered. Reloading cannot
            # restore innerText and would wipe attached store state, so never
            # heal a page whose DOM already has text.
            try:
                tc_raw = client.evaluate(
                    page,
                    "(() => ({ n: (document.body?.textContent?.trim() || '').length }))()",
                    timeout_sec=5.0,
                )
                tc_state = _coerce_evaluate_result(tc_raw)
                dom_hidden = int(tc_state.get("n") or 0) > 0
            except (RuntimeError, TimeoutError, OSError):
                dom_hidden = True
        if (
            page_url
            and reload_passes < max_reload_passes
            and last.get("errorOverlay") is True
            and polls in {3, 9, 27, 60}
            and not dom_hidden
        ):
            # Shared dev hot reload can invalidate Turbopack chunks mid-wait; the
            # page then mounts a Next.js error overlay and React never hydrates
            # the store. Bypass the browser cache (about:blank → target) so the
            # freshly compiled bundle is pulled instead of failing the poll.
            reload_passes += 1
            dom_hidden = False
            touch_wall_progress(current_node="wait_for_state_overlay_heal")
            _trigger_attach_client_warmup_once(page_url=page_url if isinstance(page_url, str) else None)
            reload_mcp_page(
                client,
                page,
                target_url=page_url,
                timeout_ms=max(reload_timeout_ms, 90_000),
                ignore_cache=True,
            )
            dismiss_blocking_modals(client, page, recover_url=page_url)
            continue
        if page_url and reload_passes < max_reload_passes and body_probe == 0 and not dom_hidden and polls in {2, 5, 10, 20, 40}:
            reload_passes += 1
            dom_hidden = False
            touch_wall_progress(current_node="wait_for_state_empty_body_heal")
            _trigger_attach_client_warmup_once(page_url=page_url if isinstance(page_url, str) else None)
            if settings_route:
                _heal_settings_deferred_loading(client, page, page_url=page_url)
            else:
                reload_mcp_page(client, page, target_url=page_url, timeout_ms=reload_timeout_ms)
                dismiss_blocking_modals(client, page, recover_url=page_url)
            continue
        if blank_heal_mode == "direct" and polls in {4, 12, 24} and last.get("hasAppLayout") is not True and body_probe < 80:
            _trigger_attach_client_warmup_once(page_url=page_url if isinstance(page_url, str) else None)
        if (
            page_url
            and reload_passes < max_reload_passes
            and blank_heal_mode == "direct"
            and polls in {4, 8, 16, 32, 56}
            and not dom_hidden
            and (_state_looks_blank(last) or last.get("deferredLoading") is True)
        ):
            reload_passes += 1
            dom_hidden = False
            touch_wall_progress(current_node="wait_for_state_deferred_heal")
            _trigger_attach_client_warmup_once(page_url=page_url if isinstance(page_url, str) else None)
            reload_mcp_page(client, page, target_url=page_url, timeout_ms=reload_timeout_ms)
            dismiss_blocking_modals(client, page, recover_url=page_url)
            continue
        if (
            page_url
            and reload_passes < max_reload_passes
            and polls in {16, 48, 96, 160}
            and not dom_hidden
            and _state_looks_blank(last)
        ):
            reload_passes += 1
            dom_hidden = False
            touch_wall_progress(current_node="wait_for_state_blank_heal")
            try:
                if blank_heal_mode == "direct" or settings_route:
                    reload_mcp_page(
                        client,
                        page,
                        target_url=page_url,
                        timeout_ms=reload_timeout_ms,
                    )
                    dismiss_blocking_modals(client, page, recover_url=page_url)
                else:
                    client.navigate(page, ui_home, timeout_ms=90_000)
                    time.sleep(2.0)
                    dismiss_blocking_modals(client, page)
                    wait_for_react_e2e_bridge(
                        client,
                        page,
                        timeout_sec=min(60.0, max(5.0, deadline - time.monotonic())),
                        page_url=ui_home,
                    )
                    client.navigate(page, page_url, timeout_ms=90_000)
                    dismiss_blocking_modals(client, page)
            except (RuntimeError, TimeoutError, OSError, AssertionError):
                reload_mcp_page(client, page, target_url=page_url, timeout_ms=reload_timeout_ms)
                dismiss_blocking_modals(client, page, recover_url=page_url)
            continue
        time.sleep(0.25)
    raise AssertionError(f"Browser state did not become ready: {last}")
