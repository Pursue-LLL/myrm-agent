"""Reload or navigate a page and re-bind the isolated private runtime that a reload wipes."""

from __future__ import annotations

import json
import os
import time

from cdp_chat.support import (
    e2e_api_base_inject_js,
    e2e_runtime_binding,
    e2e_runtime_binding_source,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)
from chrome_mcp.client import ChromeMcpClient, McpPage
from dev_gate.contract import SIGNOFF_SHPOIB_REBIND_WALL_SEC, is_e2e_signoff_runtime, shpoib_rebind_location_wait_cap_sec
from e2e_core.dev_ports import is_shared_api_base

from .parallel_load import _parallel_open_page_peer_count


def _wait_for_shpoib_runtime_ready(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 60.0,
) -> None:
    """Wait until mux-injected private Backend binding is healthy after reload."""
    # Imported at call time: wait_state imports this module (wait_for_state heals through reload_mcp_page).
    from .wait_state import wait_for_state

    wait_for_state(
        client,
        page,
        """(async () => {
          if (typeof window.__MYRM_E2E_RUNTIME_READY__ === 'undefined') {
            return { ready: false, phase: 'missing' };
          }
          try {
            await window.__MYRM_E2E_RUNTIME_READY__;
            return { ready: true };
          } catch (error) {
            return { ready: false, phase: 'error', error: String(error) };
          }
        })()""",
        timeout_sec=timeout_sec,
    )


def _is_isolated_stack() -> bool:
    """Isolated stacks reach their private API through Next rewrites, so a page needs no SHPOIB rebind (TAB-6b)."""
    return os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1"


def _reapply_shpoib_runtime_after_reload(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    target_url: str | None = None,
    timeout_sec: float = 120.0,
) -> None:
    """Reload clears window globals; re-inject binding on UI origin then bootstrap private API."""
    import os

    # Imported at call time: wait_state imports this module (wait_for_state heals through reload_mcp_page).
    from .wait_state import wait_for_state

    api_base = get_e2e_api_url()
    bootstrap_js = e2e_runtime_bootstrap_apply_js()
    binding_source = e2e_runtime_binding_source()
    if is_e2e_signoff_runtime():
        timeout_sec = max(timeout_sec, float(SIGNOFF_SHPOIB_REBIND_WALL_SEC))
    parallel_peers = _parallel_open_page_peer_count()
    if parallel_peers >= 2:
        rebind_cap = 420.0 if is_e2e_signoff_runtime() else 300.0
        timeout_sec = min(timeout_sec + parallel_peers * 15.0, rebind_cap)
    deadline = time.monotonic() + timeout_sec
    normalized_target = _normalize_rebind_target_url(target_url)
    if bootstrap_js is None:
        raise RuntimeError("SHPOIB bootstrap JS missing after reload")
    last_observed: dict[str, object] = {"phase": "not_started"}
    max_attempts = 5
    for attempt in range(max_attempts):
        remaining = max(0.0, deadline - time.monotonic())
        if remaining <= 0:
            break
        if not wait_e2e_provider_ready(api_url=api_base, timeout_sec=min(30.0, max(5.0, remaining))):
            time.sleep(2.0)
            continue
        nav_timeout_ms = min(int(remaining * 1000), 120_000)
        if binding_source is not None and normalized_target:
            client.evaluate(
                page,
                f"(() => {{{binding_source} return true; }})()",
                timeout_sec=min(30.0, max(5.0, remaining)),
            )
            client.navigate(page, normalized_target, timeout_ms=nav_timeout_ms)
            location_prefix = json.dumps(normalized_target.split("?", 1)[0])
            wait_for_state(
                client,
                page,
                f"""(() => ({{
                  ready: window.location.href.startsWith({location_prefix}),
                }}))()""",
                timeout_sec=min(_shpoib_rebind_location_wait_cap(), max(5.0, remaining)),
            )
        observed = client.evaluate(
            page,
            bootstrap_js,
            timeout_sec=min(60.0, max(5.0, remaining)),
        )
        if isinstance(observed, dict) and observed.get("ok") is True:
            rebind_timeout = float(os.environ.get("MYRM_SHPOIB_REBIND_TIMEOUT_SEC", str(timeout_sec)))
            _wait_for_shpoib_runtime_ready(client, page, timeout_sec=min(rebind_timeout, remaining))
            return
        last_observed = observed if isinstance(observed, dict) else {"value": observed}
        error_text = str(last_observed.get("error", last_observed)) if isinstance(last_observed, dict) else str(last_observed)
        transient = "failed to fetch" in error_text.lower()
        if transient and attempt + 1 < max_attempts:
            wait_e2e_provider_ready(api_url=api_base, timeout_sec=min(30.0, max(5.0, remaining)))
            time.sleep(2.0 * (attempt + 1))
            continue
        if not transient:
            break
        time.sleep(2.0)
    raise RuntimeError(f"SHPOIB runtime rebind after reload failed: {last_observed}")


def _normalize_rebind_target_url(url: str | None) -> str | None:
    if not url:
        return None
    cleaned = url.strip()
    if cleaned in ("about:blank", "undefined", "null"):
        return None
    if cleaned.startswith("http://") or cleaned.startswith("https://"):
        return cleaned
    return None


def _resolve_page_target_url(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 15.0,
) -> str | None:
    """Best-effort current document URL for SHPOIB rebind after reload."""
    try:
        href = client.evaluate(page, "window.location.href", timeout_sec=timeout_sec)
    except (RuntimeError, TimeoutError):
        href = None
    if isinstance(href, str):
        normalized = _normalize_rebind_target_url(href)
        if normalized:
            return normalized
    if isinstance(href, dict):
        raw = href.get("value")
        if isinstance(raw, str):
            normalized = _normalize_rebind_target_url(raw)
            if normalized:
                return normalized
    try:
        path = client.evaluate(
            page,
            "window.location.pathname + window.location.search + window.location.hash",
            timeout_sec=timeout_sec,
        )
    except (RuntimeError, TimeoutError):
        path = None
    if isinstance(path, str) and path.startswith("/"):
        return f"{get_e2e_ui_url().rstrip('/')}{path}"
    stored = _normalize_rebind_target_url(page.url)
    if stored:
        return stored
    return None


def reload_mcp_page(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_ms: int = 60_000,
    target_url: str | None = None,
    ignore_cache: bool = False,
) -> None:
    """Full page reload with SHPOIB runtime rebind when private backend is active.

    ``ignore_cache=True`` forces a cache-bypassing reload: stale Turbopack chunks
    on long-lived warm-shell pages can mount an outdated ``__MYRM_E2E_CHAT__``
    bridge (missing attachToChat/syncSearchServicesFromE2eApi), stranding the
    shared-UI contract.

    ``window.location.reload(true)`` is a no-op in Chrome (the ``forceGet``
    argument is Firefox-only and silently ignored), so a plain reload keeps
    serving the cached HTML/chunk set. Two-step navigation (about:blank then
    target) discards the old document and pulls freshly compiled, content-hashed
    bundle URLs.
    """
    if ignore_cache and isinstance(target_url, str) and target_url.strip():
        client.navigate(page, "about:blank", timeout_ms=min(timeout_ms, 30_000))
        client.navigate(page, target_url, timeout_ms=timeout_ms)
    else:
        client.reload(page, timeout_ms=timeout_ms)
    if e2e_runtime_binding() is not None and not _is_isolated_stack():
        resolved_url = _normalize_rebind_target_url(target_url)
        if resolved_url is None:
            resolved_url = _resolve_page_target_url(client, page, timeout_sec=min(30.0, timeout_ms / 1000))
        _reapply_shpoib_runtime_after_reload(client, page, target_url=resolved_url)


def navigate_mcp_page(
    client: ChromeMcpClient,
    page: McpPage,
    url: str,
    *,
    timeout_ms: int = 90_000,
) -> None:
    """Navigate preserving SHPOIB private API binding (full reload clears window globals).

    An isolated stack reaches its API through Next rewrites, so it navigates directly.
    """
    if _is_isolated_stack():
        client.navigate(page, url, timeout_ms=timeout_ms)
        return
    if e2e_runtime_binding() is not None:
        _reapply_shpoib_runtime_after_reload(
            client,
            page,
            target_url=url,
            timeout_sec=min(120.0, timeout_ms / 1000),
        )
        return
    api_base = get_e2e_api_url().rstrip("/")
    if not is_shared_api_base(api_base):
        client.evaluate(
            page,
            e2e_api_base_inject_js(),
            timeout_sec=min(15.0, timeout_ms / 1000),
        )
    client.navigate(page, url, timeout_ms=timeout_ms)


def _shpoib_rebind_location_wait_cap() -> float:
    return shpoib_rebind_location_wait_cap_sec()
