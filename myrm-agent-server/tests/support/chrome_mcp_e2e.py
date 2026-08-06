"""Shared real-Chrome MCP helpers for formal UI E2E tests."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from pathlib import Path

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from cdp_chat_support import (
    DISMISS_MODALS_JS,
    _e2e_api_urlopen,
    e2e_runtime_binding,
    e2e_runtime_binding_source,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_cdp_ready,
    wait_e2e_provider_ready,
)  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate_contract import (
    MUX_RECLAIM_STALL_TOKEN,
    SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC,
    SIGNOFF_SHPOIB_REBIND_WALL_SEC,
    is_e2e_signoff_runtime,
    shpoib_rebind_location_wait_cap_sec,
)  # noqa: E402
from e2e_orchestrator import touch_wall_progress  # noqa: E402
from e2e_shared_ui_hydrate import (  # noqa: E402
    parallel_shared_ui_hydrate_queue_enabled,
    shared_ui_hydrate_slot,
)
from e2e_warm_ui_heal import heal_shared_frontend_debounced  # noqa: E402

from tests.support.e2e_runtime_guard import heartbeat_e2e_lease  # noqa: E402

__all__ = [
    "ChromeMcpClient",
    "McpPage",
    "_reapply_shpoib_runtime_after_reload",
    "dismiss_blocking_modals",
    "e2e_runtime_binding",
    "ensure_desktop_viewport",
    "get_e2e_api_url",
    "get_e2e_ui_url",
    "guarded_httpx_request",
    "http_json",
    "open_mcp_page",
    "open_mcp_page_async",
    "OpenMcpPageSession",
    "prepare_e2e_ui_session",
    "reload_mcp_page",
    "wait_for_react_e2e_bridge",
    "wait_for_state",
    "warm_ui_route",
]

_ENSURE_DESKTOP_VIEWPORT_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore — some profiles block resizeTo
  }
  return { width: window.innerWidth, height: window.innerHeight };
})()"""


def ensure_desktop_viewport(
    client: ChromeMcpClient, page: McpPage
) -> dict[str, object]:
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
    """Dismiss onboarding/migration overlays that block E2E clicks (SSOT: cdp_chat_support)."""
    target_url = recover_url or getattr(page, "url", None)
    last: dict[str, object] = {}
    for attempt in range(3):
        raw = client.evaluate(page, _LOCALHOST_PAGE_JS, timeout_sec=15.0)
        last = _coerce_evaluate_result(raw)
        href = str(last.get("href", ""))
        if last.get("ready") is True and "chrome-error://" not in href:
            break
        if attempt >= 2 or not isinstance(target_url, str) or not target_url.strip():
            raise AssertionError(
                f"Page not on localhost after chrome-error recovery: {last}"
            )
        reload_mcp_page(client, page, target_url=target_url, timeout_ms=90_000)
    dismissed = client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
    assert isinstance(dismissed, dict) and dismissed.get("ok") is True, dismissed


def prepare_e2e_ui_session(api_url: str) -> None:
    """Mark onboarding complete so PageLayout does not overlay the chat during E2E.

    READ-scoped tests must not mutate global config; they rely on dismiss_blocking_modals
    localStorage boot flags instead (P0-C effect guard).
    """
    from e2e_effect_guard import current_access_scope

    if current_access_scope() == "READ":
        return
    http_json(
        "POST",
        f"{api_url}/api/v1/config/onboarding/complete",
        expected_statuses=frozenset({200, 201}),
    )


def guarded_httpx_request(
    client: object, method: str, url: str, **kwargs: object
) -> object:
    """Effect-guarded httpx request for formal chrome_e2e live agent paths."""
    from e2e_effect_guard import guarded_httpx_request as _guard

    return _guard(client, method, url, **kwargs)


def http_json(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
) -> object:
    from e2e_effect_guard import assert_http_effect_allowed

    assert_http_effect_allowed(method=method, url=url)
    allowed_bases = [get_e2e_ui_url(), get_e2e_api_url()]
    port_raw = os.environ.get("MYRM_BACKEND_PORT", "8080").strip()
    shared_hot = f"http://127.0.0.1:{port_raw if port_raw.isdigit() else 8080}"
    if shared_hot.rstrip("/") not in {base.rstrip("/") for base in allowed_bases}:
        allowed_bases.append(shared_hot)
    allowed = tuple(allowed_bases)
    if not url.startswith(allowed):
        raise ValueError(
            f"Chrome E2E HTTP helper only permits loopback app URLs: {url}"
        )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(  # noqa: S310 - validated loopback
        url, data=data, method=method
    )
    if data is not None:
        request.add_header("Content-Type", "application/json")
    try:
        response = _e2e_api_urlopen(
            request,
            timeout_sec=30.0,
            max_attempts=3,
        )  # noqa: S310 - loopback only
        with response as http_response:
            raw = http_response.read()
            status = http_response.status
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = exc.code
    if status not in expected_statuses:
        raise RuntimeError(f"HTTP {method} {url} returned {status}: {raw[:500]!r}")
    return json.loads(raw) if raw else {}


def _warm_ui_parallel_wait_sec(base_wait_sec: float) -> float:
    """Extend warm budget when wave leases or parallel chrome_e2e peers contend for shared UI."""
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            # Flock serializes compile bursts — do not multiply per-lane wall by peer count.
            return base_wait_sec
    except ImportError:
        pass
    monorepo_root = Path(__file__).resolve().parents[4]
    try:
        from dev_gate_contract import (
            phase_c_burst_lane_count,
            shared_ui_hydrate_wait_sec,
        )
        from stack_mutation_policy import wave_active_lease_count
        from transport_supervisor import parallel_active_test_count

        burst_lanes = phase_c_burst_lane_count()
        wave_leases = wave_active_lease_count(monorepo_root)
        active_tests = parallel_active_test_count()
        if burst_lanes >= 2:
            # Phase C burst: scale by declared lane width, not foreign daily peers.
            active = max(burst_lanes, min(wave_leases, burst_lanes + 1))
        else:
            active = max(wave_leases, active_tests)
        if active > 0:
            cap = float(shared_ui_hydrate_wait_sec())
            return min(base_wait_sec + active * 45.0, cap)
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return base_wait_sec


def warm_ui_route(path: str, *, timeout_sec: float | None = None) -> None:
    """HTTP GET a UI route so webpack/turbopack compiles before Chrome navigation."""
    import os

    if not path.startswith("/"):
        raise ValueError(f"warm_ui_route expects an absolute path, got: {path!r}")
    url = f"{get_e2e_ui_url()}{path}"
    try:
        from warm_shell_registry import platform_shell_fresh, seal_platform_shell

        if platform_shell_fresh(route_path=path):
            heartbeat_e2e_lease()
            touch_wall_progress(current_node="warm_ui_route_skipped_registry_reuse")
            request = urllib.request.Request(url, method="GET")  # noqa: S310
            try:
                with urllib.request.urlopen(request, timeout=5.0) as response:  # noqa: S310
                    if int(response.status) == 200:
                        seal_platform_shell(ui_url=url, route_path=path)
                        return
            except (
                urllib.error.HTTPError,
                urllib.error.URLError,
                TimeoutError,
                OSError,
            ):
                pass
    except ImportError:
        pass
    base_wait = (
        timeout_sec
        if timeout_sec is not None
        else float(os.environ.get("MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC", "180"))
    )
    wait_sec = _warm_ui_parallel_wait_sec(base_wait)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        wait_sec = min(wait_sec, 120.0)
    poll_sec = float(os.environ.get("MYRM_CHROME_E2E_SHARED_UI_POLL_SEC", "2"))
    deadline = time.monotonic() + wait_sec
    last_error: BaseException | None = None
    heal_interval = 30.0
    next_heal_at = time.monotonic() + heal_interval
    monorepo_root = Path(__file__).resolve().parents[4]

    def _heal_shared_frontend() -> None:
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
            return
        heal_shared_frontend_debounced(
            monorepo_root,
            debounce_sec=60.0,
            subprocess_timeout_sec=60.0,
        )

    def _attempt_warm_get() -> bool:
        """Single GET attempt; True when HTTP 200."""
        nonlocal last_error, next_heal_at
        heartbeat_e2e_lease()
        touch_wall_progress(current_node="warm_ui_route")
        if time.monotonic() >= next_heal_at:
            next_heal_at = time.monotonic() + heal_interval
            _heal_shared_frontend()
        request = urllib.request.Request(  # noqa: S310 - loopback only
            url, method="GET"
        )
        per_attempt = max(3.0, min(10.0, deadline - time.monotonic()))

        def _do_get() -> int:
            with urllib.request.urlopen(  # noqa: S310
                request, timeout=per_attempt
            ) as response:
                return int(response.status)

        try:
            if parallel_shared_ui_hydrate_queue_enabled():
                with shared_ui_hydrate_slot():
                    status = _do_get()
            else:
                status = _do_get()
            if status == 200:
                try:
                    from warm_shell_registry import seal_platform_shell

                    seal_platform_shell(ui_url=url, route_path=path)
                except ImportError:
                    pass
                return True
            last_error = RuntimeError(f"warm_ui_route GET {url} returned HTTP {status}")
            if status in {404, 502, 503}:
                _heal_shared_frontend()
                next_heal_at = time.monotonic() + heal_interval
        except urllib.error.HTTPError as exc:
            if exc.code in {404, 502, 503}:
                last_error = exc
                _heal_shared_frontend()
                next_heal_at = time.monotonic() + heal_interval
            else:
                last_error = exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            _heal_shared_frontend()
            next_heal_at = time.monotonic() + heal_interval
        return False

    def _warm_ui_poll_loop() -> None:
        while time.monotonic() < deadline:
            if _attempt_warm_get():
                return
            time.sleep(poll_sec)
        warm_error = RuntimeError(
            f"warm_ui_route GET {url} failed after {wait_sec:.0f}s: {last_error!r}"
        )
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
            print(
                f"E2E_WARM_UI_SOFT_SKIP: signoff defers compile to Chrome bootstrap — {warm_error}",
                file=sys.stderr,
                flush=True,
            )
            touch_wall_progress(current_node="warm_ui_route_soft_skip")
            return
        raise warm_error

    _warm_ui_poll_loop()


def _wait_for_shpoib_runtime_ready(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 60.0,
) -> None:
    """Wait until mux-injected private Backend binding is healthy after reload."""
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


def _reapply_shpoib_runtime_after_reload(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    target_url: str | None = None,
    timeout_sec: float = 120.0,
) -> None:
    """Reload clears window globals; re-inject binding on UI origin then bootstrap private API."""
    import os

    api_base = get_e2e_api_url()
    bootstrap_js = e2e_runtime_bootstrap_apply_js()
    binding_source = e2e_runtime_binding_source()
    if bootstrap_js is None and binding_source is None:
        raise RuntimeError("SHPOIB bootstrap JS missing after reload")
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
        if not wait_e2e_provider_ready(
            api_url=api_base, timeout_sec=min(30.0, max(5.0, remaining))
        ):
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
                timeout_sec=min(
                    _shpoib_rebind_location_wait_cap(), max(5.0, remaining)
                ),
            )
        observed = client.evaluate(
            page,
            bootstrap_js,
            timeout_sec=min(60.0, max(5.0, remaining)),
        )
        if isinstance(observed, dict) and observed.get("ok") is True:
            rebind_timeout = float(
                os.environ.get("MYRM_SHPOIB_REBIND_TIMEOUT_SEC", str(timeout_sec))
            )
            _wait_for_shpoib_runtime_ready(
                client, page, timeout_sec=min(rebind_timeout, remaining)
            )
            return
        last_observed = observed if isinstance(observed, dict) else {"value": observed}
        error_text = (
            str(last_observed.get("error", last_observed))
            if isinstance(last_observed, dict)
            else str(last_observed)
        )
        transient = "failed to fetch" in error_text.lower()
        if transient and attempt + 1 < max_attempts:
            wait_e2e_provider_ready(
                api_url=api_base, timeout_sec=min(30.0, max(5.0, remaining))
            )
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
) -> None:
    """Full page reload with SHPOIB runtime rebind when private backend is active."""
    client.reload(page, timeout_ms=timeout_ms)
    if e2e_runtime_binding() is not None:
        resolved_url = _normalize_rebind_target_url(target_url)
        if resolved_url is None:
            resolved_url = _resolve_page_target_url(
                client, page, timeout_sec=min(30.0, timeout_ms / 1000)
            )
        _reapply_shpoib_runtime_after_reload(client, page, target_url=resolved_url)


_OPEN_PAGE_REQUEST_TIMEOUT_SEC = 60.0
_OPEN_PAGE_NEW_PAGE_TIMEOUT_MS = 120_000
_OPEN_PAGE_ATTEMPTS = 2
_OPEN_PAGE_LAYOUT_WAIT_SEC = 120.0
_OPEN_PAGE_WALL_BUDGET_SEC = 150.0
_OPEN_PAGE_TOTAL_BUDGET_SEC = 280.0
_OPEN_PAGE_BODY_FRACTION = 0.35
_OPEN_PAGE_BODY_FRACTION_WALL_RATIO = 0.55
_OPEN_PAGE_BODY_FRACTION_FLOOR_SEC = 90.0
_PROGRESS_HEARTBEAT_INTERVAL_SEC = 15.0
_TRANSPORT_PROGRESS_INTERVAL_SEC = 30.0


def _emit_transport_progress(*, current_node: str, node_started: float) -> None:
    from dev_gate_contract import E2E_TRANSPORT_PROGRESS_TOKEN

    elapsed = time.monotonic() - node_started
    print(
        f"{E2E_TRANSPORT_PROGRESS_TOKEN}: node={current_node} "
        f"node_elapsed={int(elapsed)}s (do not stop other pytest)",
        file=sys.stderr,
        flush=True,
    )


@contextmanager
def _blocking_progress_loop(
    *,
    current_node: str,
    transport_session_started: float | None = None,
) -> Iterator[None]:
    """Keep lease + wall progress fresh while mux MCP calls may block (anti hung-reap)."""
    import os
    import signal

    from dev_gate_contract import signoff_open_page_transport_stall_cap_sec
    from e2e_stall_guard import assert_transport_node_not_stuck, transport_stall_cap_sec

    del transport_session_started
    stop = threading.Event()
    node_started = time.monotonic()
    last_transport_emit = node_started
    (
        _client_timeout,
        _page_timeout_ms,
        _wall_budget,
        open_page_total_budget,
        _attempts,
    ) = _open_page_parallel_budgets(
        _OPEN_PAGE_REQUEST_TIMEOUT_SEC,
        new_page_timeout_ms=_OPEN_PAGE_NEW_PAGE_TIMEOUT_MS,
    )
    if is_e2e_signoff_runtime():
        # R181: do not min() against per-attempt transport budget — signoff stall cap
        # already scales with MYRM_E2E_SIGNOFF_BATCH_BODY_SEC (R179/R180).
        stall_cap = signoff_open_page_transport_stall_cap_sec()
    else:
        stall_cap = max(transport_stall_cap_sec(), open_page_total_budget + 15.0)
        if _parallel_open_page_peer_count() >= 2:
            # R170: mux queue may block longer than NODE_STUCK peer cap — use body
            # fraction budget so parallel LIVE can reach outer transport retry.
            stall_cap = max(
                transport_stall_cap_sec(),
                _open_page_body_fraction_cap_sec(),
            )
    try:
        from e2e_session_lifecycle import current_phase

        if current_phase() == "bootstrap":
            if is_e2e_signoff_runtime() or _dev_private_shpoib_bootstrap_phase():
                from dev_gate_contract import signoff_bootstrap_transport_stall_cap_sec

                # R220/R222: dev PRIVATE SHPOIB bootstrap — align stall with mux queue headroom.
                stall_cap = max(
                    stall_cap,
                    signoff_bootstrap_transport_stall_cap_sec(
                        parallel_peers=_parallel_open_page_peer_count(),
                        page_timeout_ms=min(_OPEN_PAGE_NEW_PAGE_TIMEOUT_MS, 90_000),
                    ),
                )
            else:
                from transport_supervisor import bootstrap_wall_cap_sec

                bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=True))
                stall_cap = min(stall_cap, bootstrap_cap)
    except ImportError:
        pass

    def _loop() -> None:
        nonlocal last_transport_emit
        while not stop.wait(_PROGRESS_HEARTBEAT_INTERVAL_SEC):
            try:
                assert_transport_node_not_stuck(
                    current_node=current_node,
                    node_started=node_started,
                    stall_cap=stall_cap,
                )
            except RuntimeError:
                # Stall tripwire must interrupt the main thread blocked in MCP I/O.
                os.kill(os.getpid(), signal.SIGINT)
                continue
            heartbeat_e2e_lease()
            touch_wall_progress(current_node=current_node)
            now = time.monotonic()
            if now - last_transport_emit >= _TRANSPORT_PROGRESS_INTERVAL_SEC:
                _emit_transport_progress(
                    current_node=current_node, node_started=node_started
                )
                last_transport_emit = now

    worker = threading.Thread(target=_loop, name="open-mcp-page-progress", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2.0)


def _open_page_body_fraction_cap_sec() -> float:
    """R143: open_mcp_page must not consume more than 35% of LIVE BODY wall."""
    try:
        if is_e2e_signoff_runtime():
            from dev_gate_contract import signoff_effective_body_wall_sec

            body_cap = float(signoff_effective_body_wall_sec())
        else:
            from transport_supervisor import live_agent_body_wall_cap_sec

            body_cap = float(live_agent_body_wall_cap_sec())
    except ImportError:
        body_cap = 600.0
    base = max(
        _OPEN_PAGE_BODY_FRACTION_FLOOR_SEC,
        body_cap * _OPEN_PAGE_BODY_FRACTION,
    )
    peers = _parallel_open_page_peer_count()
    if peers >= 2:
        return min(base + peers * 25.0, body_cap * 0.45)
    return base


def _open_page_layout_wait_sec() -> float:
    peers = _parallel_open_page_peer_count()
    if is_e2e_signoff_runtime():
        base = float(SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC)
        if peers >= 1:
            return min(base + peers * 15.0, 300.0)
        return base
    base = _OPEN_PAGE_LAYOUT_WAIT_SEC
    if peers >= 1:
        try:
            from dev_gate_contract import shared_ui_hydrate_wait_sec

            cap = float(shared_ui_hydrate_wait_sec())
            return min(base + peers * 30.0, cap)
        except ImportError:
            return min(base + peers * 30.0, 240.0)
    return base


_APP_LAYOUT_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="app-layout"]'),
  pathname: location.pathname,
  title: document.title,
  bodyLen: document.body?.innerText?.length ?? 0,
  kind: 'app',
}))()"""

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


def _wait_for_app_layout_open(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    url: str,
    timeout_ms: int,
) -> None:
    """Wait for page shell (AppLayout or SettingsLayout); signoff reload-heals stale mux tabs."""
    shell_ready_js = _page_shell_ready_js_for_url(url)
    layout_timeout = _open_page_layout_wait_sec()
    signoff = is_e2e_signoff_runtime()
    heal_passes = 3 if signoff or _shared_read_parallel_open_page_retry_allowed() else 2
    last_exc: AssertionError | None = None

    for attempt in range(heal_passes):
        client.set_tool_wall_deadline(None)
        if attempt > 0:
            reload_mcp_page(client, page, target_url=url, timeout_ms=timeout_ms)
            if signoff:
                ensure_desktop_viewport(client, page)
                dismiss_blocking_modals(client, page)
            client.set_tool_wall_deadline(None)
        attempt_timeout = (
            layout_timeout
            if signoff or attempt == 0
            else min(120.0, layout_timeout * 0.5)
        )
        try:
            wait_for_state(
                client,
                page,
                shell_ready_js,
                timeout_sec=attempt_timeout,
            )
            return
        except AssertionError as exc:
            last_exc = exc
            if (
                not signoff
                and attempt == 0
                and e2e_runtime_binding() is None
                and not _shared_read_parallel_open_page_retry_allowed()
            ):
                raise

    detail = last_exc.args[0] if last_exc is not None else "unknown"
    raise AssertionError(
        f"Page shell did not hydrate after {heal_passes} reload-heal attempt(s): {detail}"
    ) from last_exc


def _shpoib_rebind_location_wait_cap() -> float:
    return shpoib_rebind_location_wait_cap_sec()


def _shared_read_parallel_open_page_retry_allowed() -> bool:
    """SHARED READ lane needs mux reload-heal under parallel SMP defer (blank shell)."""
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    if lane != "READ":
        return False
    return os.environ.get("MYRM_E2E_SHARED_HOT", "").strip() != "1"


def _open_page_parallel_retry_allowed() -> bool:
    """Signoff, dev PRIVATE SHPOIB bootstrap, and SHARED READ share mux-heal retry under parallel peers."""
    return (
        is_e2e_signoff_runtime()
        or _dev_private_shpoib_bootstrap_phase()
        or _shared_read_parallel_open_page_retry_allowed()
    )


def _open_page_attempt_count() -> int:
    """R152 TPMc: parallel mux — single outer pass; no retry that resets session clock."""
    peers = _parallel_open_page_peer_count()
    if _open_page_parallel_retry_allowed():
        # R171/R223: heavy mux — fewer attempts, more wall per attempt beats 3× short stalls.
        if peers >= 4:
            return 2
        if peers >= 3:
            return 3
        return 2
    if peers >= 2:
        return 1
    return _OPEN_PAGE_ATTEMPTS


def _restart_open_page_mux_budget(
    *,
    open_page_wall_budget_sec: float,
    open_page_total_budget_sec: float,
) -> tuple[float, float, float]:
    """Reset open_mcp_page clocks after mux restart for signoff retry."""
    heartbeat_e2e_lease()
    touch_wall_progress(current_node="open_mcp_page_mux_retry")
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        transport_session_started = time.monotonic()
        return (
            transport_session_started,
            transport_session_started + open_page_wall_budget_sec,
            transport_session_started + open_page_total_budget_sec,
        )
    _force_mux_attach_restart_after_new_page_timeout()
    try:
        ChromeMcpClient().recover_mux_transport()
    except RuntimeError:
        pass
    cdp_budget = _open_page_cdp_probe_budget_sec()
    _require_e2e_cdp_ready(budget_sec=cdp_budget)
    time.sleep(min(5.0, max(2.0, cdp_budget * 0.05)))
    try:
        drain_budget = _mux_cold_attach_drain_budget_sec()
        _wait_mux_cold_attach_drain(budget_sec=drain_budget)
    except RuntimeError:
        pass
    transport_session_started = time.monotonic()
    return (
        transport_session_started,
        transport_session_started + open_page_wall_budget_sec,
        transport_session_started + open_page_total_budget_sec,
    )


def _mux_transport_wait_budget_sec() -> float:
    """Mux queue wait — pessimistic under signoff bootstrap parallel (R219)."""
    try:
        from dev_gate_contract import signoff_mux_transport_wait_budget_sec

        return signoff_mux_transport_wait_budget_sec()
    except ImportError:
        from transport_supervisor import mux_upstream_wait_cap

        return float(mux_upstream_wait_cap())


def _shared_read_bootstrap_phase() -> bool:
    """Dev SHARED READ bootstrap — mux queue must not consume open_mcp_page attempt budget."""
    if os.environ.get("MYRM_E2E_LANE", "").strip().upper() != "READ":
        return False
    if os.environ.get("MYRM_E2E_EXECUTION_MODE", "").strip().upper() != "SHARED":
        return False
    try:
        from e2e_session_lifecycle import current_phase

        return current_phase() == "bootstrap"
    except ImportError:
        return False


def _open_page_queue_wait_extends_deadlines() -> bool:
    """P0-C: bootstrap mux fair-queue wait must not consume open_mcp_page attempt budget."""
    if _dev_private_shpoib_bootstrap_phase():
        return True
    if _shared_read_bootstrap_phase():
        return True
    if is_e2e_signoff_runtime():
        try:
            from e2e_session_lifecycle import current_phase

            return current_phase() == "bootstrap"
        except ImportError:
            return False
    return False


def _extend_open_page_deadlines_for_queue_wait(
    *,
    elapsed_sec: float,
    transport_session_started: float,
    wall_deadline: float,
    total_deadline: float,
) -> tuple[float, float, float]:
    if elapsed_sec <= 0.0 or not _open_page_queue_wait_extends_deadlines():
        return transport_session_started, wall_deadline, total_deadline
    return (
        transport_session_started,
        wall_deadline + elapsed_sec,
        total_deadline + elapsed_sec,
    )


def _wait_open_page_mux_turn(
    *,
    budget_sec: float,
    current_node: str,
    transport_session_started: float,
    wall_deadline: float,
    total_deadline: float,
) -> tuple[float, float, float]:
    from browser_orchestrator import wait_for_operation_credit

    wait_started = time.monotonic()
    wait_for_operation_credit(budget_sec=budget_sec, current_node=current_node)
    return _extend_open_page_deadlines_for_queue_wait(
        elapsed_sec=time.monotonic() - wait_started,
        transport_session_started=transport_session_started,
        wall_deadline=wall_deadline,
        total_deadline=total_deadline,
    )


def _dev_private_shpoib_bootstrap_phase() -> bool:
    try:
        from dev_gate_contract import private_shpoib_runtime_active
        from e2e_session_lifecycle import current_phase

        return current_phase() == "bootstrap" and private_shpoib_runtime_active()
    except ImportError:
        return False


def _open_page_parallel_budgets(
    request_timeout_sec: float,
    *,
    new_page_timeout_ms: int,
    peers: int | None = None,
) -> tuple[float, int, float, float, int]:
    """Fixed open_mcp_page budgets — scale tool wall under parallel mux contention (R122-B9)."""
    del peers
    capped_ms = min(new_page_timeout_ms, _OPEN_PAGE_NEW_PAGE_TIMEOUT_MS)
    signoff = is_e2e_signoff_runtime()
    parallel_peers = _parallel_open_page_peer_count()
    if signoff:
        from dev_gate_contract import (
            signoff_bootstrap_open_mcp_budgets,
            signoff_open_mcp_budgets,
        )

        bootstrap_phase = False
        try:
            from e2e_session_lifecycle import current_phase

            bootstrap_phase = current_phase() == "bootstrap"
        except ImportError:
            bootstrap_phase = False
        if bootstrap_phase:
            budgets = signoff_bootstrap_open_mcp_budgets(parallel_peers=parallel_peers)
        else:
            budgets = signoff_open_mcp_budgets(parallel_peers=parallel_peers)
        wall_budget = budgets.wall_budget_sec
        total_budget = budgets.total_budget_sec
        attempts = budgets.attempt_count
        if parallel_peers >= 2 and not bootstrap_phase:
            body_frac_cap = _open_page_body_fraction_cap_sec()
            total_budget = min(total_budget, body_frac_cap)
            wall_budget = min(
                wall_budget,
                body_frac_cap * _OPEN_PAGE_BODY_FRACTION_WALL_RATIO,
            )
        return (
            min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
            capped_ms,
            wall_budget,
            total_budget,
            attempts,
        )
    if _dev_private_shpoib_bootstrap_phase():
        from dev_gate_contract import signoff_bootstrap_open_mcp_budgets

        budgets = signoff_bootstrap_open_mcp_budgets(parallel_peers=parallel_peers)
        return (
            min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
            capped_ms,
            budgets.wall_budget_sec,
            budgets.total_budget_sec,
            budgets.attempt_count,
        )
    burst_raw = os.environ.get("MYRM_E2E_PHASE_C_BURST_LANES", "").strip()
    if burst_raw.isdigit() and int(burst_raw) >= 4:
        from dev_gate_contract import signoff_open_mcp_budgets

        budgets = signoff_open_mcp_budgets(parallel_peers=int(burst_raw))
        return (
            min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
            capped_ms,
            budgets.wall_budget_sec,
            budgets.total_budget_sec,
            budgets.attempt_count,
        )
    wall_budget = _OPEN_PAGE_WALL_BUDGET_SEC
    total_budget = _OPEN_PAGE_TOTAL_BUDGET_SEC
    wall_cap = 300.0
    total_cap = 480.0
    attempts = _open_page_attempt_count()
    if parallel_peers >= 2:
        wall_budget = min(wall_budget + parallel_peers * 18.0, wall_cap)
        total_budget = min(total_budget + parallel_peers * 30.0, total_cap)
        body_frac_cap = _open_page_body_fraction_cap_sec()
        total_budget = min(total_budget, body_frac_cap)
        wall_budget = min(
            wall_budget,
            body_frac_cap * _OPEN_PAGE_BODY_FRACTION_WALL_RATIO,
        )
    return (
        min(request_timeout_sec, _OPEN_PAGE_REQUEST_TIMEOUT_SEC),
        capped_ms,
        wall_budget,
        total_budget,
        attempts,
    )


def _parallel_open_page_peer_count() -> int:
    """Wave/mux peers for open_mcp_page heal policy (R122-B8)."""
    from mux_load import parallel_open_page_peer_count

    return parallel_open_page_peer_count(signoff=is_e2e_signoff_runtime())


def _should_skip_attach_preflight_restart() -> bool:
    """P0-B: global mux attach restart must not run under active parallel load."""
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load(force=True)
        if max(0, load.mux_contexts, load.wave_leases) > 0:
            return True
    except (ImportError, OSError, TypeError, ValueError):
        pass
    return _parallel_open_page_peer_count() >= 2


def _open_page_parallel_total_wall_only() -> bool:
    """R122-B12: parallel mux — one outer total_deadline, no per-tool slice starvation."""
    return _parallel_open_page_peer_count() >= 2


def _open_page_allow_mux_budget_extension() -> bool:
    """R122-B12: parallel peers must not get hidden 3rd+ open_mcp pass via mux restart reset."""
    return not _open_page_parallel_total_wall_only()


def _force_mux_attach_restart_after_new_page_timeout() -> None:
    """Restart mux daemon when tools/list probe passes but new_page hangs (attach heal)."""
    if _should_skip_attach_preflight_restart():
        return
    import sys

    lib_dir = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="open_mcp_page new_page timeout")


def _signoff_mux_drain_budget_sec() -> float:
    """Peers-scaled mux drain budget; signoff bootstrap uses remaining wall (Phase3-C)."""
    budget = _mux_cold_attach_drain_budget_sec()
    if not is_e2e_signoff_runtime():
        return budget
    peers = _parallel_open_page_peer_count()
    if peers >= 1:
        try:
            from dev_gate_contract import signoff_open_mcp_budgets

            budget = max(
                budget,
                signoff_open_mcp_budgets(parallel_peers=peers).wall_budget_sec,
            )
        except ImportError:
            pass
    try:
        from e2e_session_lifecycle import current_phase, remaining_wall_sec

        if current_phase() == "bootstrap" and peers < 1:
            remaining = remaining_wall_sec()
            if remaining > 0:
                budget = min(max(budget, 45.0), remaining)
    except (ImportError, RuntimeError, TypeError, ValueError):
        pass
    return budget


def _wait_cold_shim_peer_pressure_drain(
    *, budget_sec: float, current_node: str
) -> None:
    """Wait until mux peer load drops below cold-shim defer threshold (R231)."""
    try:
        from transport_supervisor import (
            _cold_shim_defer_peer_load,
            cold_shim_restart_defer_peer_threshold,
        )
    except ImportError:
        return
    defer_threshold = cold_shim_restart_defer_peer_threshold()
    deadline = time.monotonic() + max(0.0, budget_sec)
    poll_sec = 1.0
    while time.monotonic() < deadline:
        peers = _cold_shim_defer_peer_load()
        if peers < defer_threshold:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        print(
            f"E2E_COLD_SHIM_PEER_WAIT: peers={peers} "
            f"threshold={defer_threshold} "
            f"remaining={remaining:.0f}s node={current_node}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(min(poll_sec, remaining))
        poll_sec = min(poll_sec * 1.2, 5.0)
    peers = _cold_shim_defer_peer_load()
    if peers >= defer_threshold:
        if is_e2e_signoff_runtime():
            print(
                f"E2E_COLD_SHIM_PEER_WAIT: peers={peers} "
                f">= {defer_threshold} after {budget_sec:.0f}s — "
                f"signoff proceed to mux recovery lock (node={current_node})",
                file=sys.stderr,
                flush=True,
            )
            return
        raise RuntimeError(
            f"E2E_COLD_SHIM_PEER_PRESSURE: defer_peer_load={peers} "
            f">= {defer_threshold} after {budget_sec:.0f}s "
            f"(node={current_node}; do not stop other pytest)"
        )


def _signoff_wait_mux_before_new_page(*, budget_sec: float | None = None) -> None:
    """Signoff pre-new_page mux gate — operation-credit transport SSOT (P0-B)."""
    from browser_orchestrator import wait_for_operation_credit

    wait_budget = float(
        budget_sec if budget_sec is not None else _signoff_mux_drain_budget_sec()
    )
    gate_started = time.monotonic()
    credit_budget = min(wait_budget, _mux_transport_wait_budget_sec())
    wait_for_operation_credit(
        budget_sec=credit_budget,
        current_node="open_mcp_page_signoff_gate",
    )
    peer_budget = max(30.0, wait_budget - (time.monotonic() - gate_started))
    _wait_cold_shim_peer_pressure_drain(
        budget_sec=peer_budget,
        current_node="open_mcp_page_signoff_peer_gate",
    )


def _signoff_threaded_new_page(
    client: ChromeMcpClient,
    url: str,
    *,
    timeout_ms: int,
    join_timeout_sec: float,
) -> McpPage:
    """Run new_page off the main thread so stall tripwire can abandon without SIGINT."""
    outcome: list[McpPage | BaseException] = []

    def _worker() -> None:
        try:
            outcome.append(client.new_page(url, timeout_ms=timeout_ms))
        except BaseException as exc:
            outcome.append(exc)

    worker = threading.Thread(
        target=_worker,
        name="signoff-new-page",
        daemon=True,
    )
    worker.start()
    from dev_gate_contract import (
        E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED_TOKEN,
        signoff_new_page_join_stall_abandon_sec,
    )

    stall_abandon_sec = signoff_new_page_join_stall_abandon_sec(
        join_timeout_sec=join_timeout_sec,
    )
    join_deadline = time.monotonic() + join_timeout_sec
    stall_deadline = time.monotonic() + stall_abandon_sec
    poll_sec = 5.0
    while worker.is_alive():
        now = time.monotonic()
        if now >= join_deadline or now >= stall_deadline:
            break
        worker.join(timeout=min(poll_sec, join_deadline - now, stall_deadline - now))
    if worker.is_alive():
        try:
            client.abandon_inflight_requests(cdp_drift=True)
        except RuntimeError:
            pass
        _force_mux_attach_restart_after_new_page_timeout()
        elapsed = min(join_timeout_sec, stall_abandon_sec)
        if time.monotonic() >= stall_deadline and time.monotonic() < join_deadline:
            elapsed = stall_abandon_sec
            print(
                f"E2E_SIGNOFF_NEW_PAGE_JOIN_STALL: "
                f"stall_abandon={stall_abandon_sec:.0f}s join_cap={join_timeout_sec:.0f}s url={url}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(
                f"{E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED_TOKEN}: "
                f"join={join_timeout_sec:.0f}s url={url}",
                file=sys.stderr,
                flush=True,
            )
        raise TimeoutError(
            f"Chrome MCP new_page thread join timed out after {elapsed:.0f}s"
        )
    if not outcome:
        raise RuntimeError("Chrome MCP new_page worker exited without result")
    result = outcome[0]
    if isinstance(result, BaseException):
        raise result
    return result


def _open_page_new_page(
    client: ChromeMcpClient,
    url: str,
    *,
    timeout_ms: int,
    attempt_wall_deadline: float,
) -> McpPage:
    if is_e2e_signoff_runtime():
        from dev_gate_contract import (
            signoff_new_page_join_timeout_sec,
            signoff_open_mcp_budgets,
        )

        signoff_open_mcp_budgets(
            parallel_peers=_parallel_open_page_peer_count(),
        )
        _signoff_wait_mux_before_new_page(
            budget_sec=_signoff_mux_drain_budget_sec(),
        )
        join_timeout_sec = signoff_new_page_join_timeout_sec(
            page_timeout_ms=timeout_ms,
            parallel_peers=_parallel_open_page_peer_count(),
        )
        return _signoff_threaded_new_page(
            client,
            url,
            timeout_ms=timeout_ms,
            join_timeout_sec=join_timeout_sec,
        )
    return client.new_page(url, timeout_ms=timeout_ms)


def _open_page_cdp_probe_budget_sec() -> float:
    """Scale CDP+mux preflight budget under parallel wave/mux load (R117)."""
    base = 45.0
    max_budget = 240.0 if is_e2e_signoff_runtime() else 180.0
    peers = 0
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load()
        peers = max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    if peers <= 0:
        monorepo_root = Path(__file__).resolve().parents[4]
        try:
            from stack_mutation_policy import wave_active_lease_count

            peers = wave_active_lease_count(monorepo_root)
        except (ImportError, OSError, RuntimeError, ValueError):
            pass
    if peers <= 0:
        return base
    return min(base + peers * 12.0, max_budget)


def _require_e2e_cdp_ready(*, budget_sec: float | None = None) -> None:
    """SSOT CDP probe for open_mcp_page — mux heal deferred to new_page R121 inner retry."""
    import os

    port = int(os.environ.get("MYRM_CHROME_E2E_PORT", "9333"))
    wait_budget = (
        budget_sec if budget_sec is not None else _open_page_cdp_probe_budget_sec()
    )
    deadline = time.monotonic() + wait_budget

    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        touch_wall_progress(current_node="open_mcp_page_cdp_probe")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if wait_e2e_cdp_ready(
            timeout_sec=min(5.0, max(1.0, remaining)),
            port=port,
        ):
            return
        time.sleep(1.0)
    raise RuntimeError(f"CDP endpoint not ready after {wait_budget:.0f}s on :{port}")


def _mux_cold_attach_drain_budget_sec() -> float:
    from dev_gate_contract import parallel_mux_cold_attach_drain_sec

    return parallel_mux_cold_attach_drain_sec(
        parallel_peers=_parallel_open_page_peer_count(),
    )


def _wait_mux_cold_attach_drain(*, budget_sec: float) -> None:
    """Wait until mux operation credits are free — orchestrator SSOT (P0-B)."""
    from browser_orchestrator import wait_for_operation_credit

    wait_for_operation_credit(
        budget_sec=budget_sec,
        current_node="open_mcp_page_mux_drain",
    )


def _retryable_open_page_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        MUX_RECLAIM_STALL_TOKEN.lower() in message
        or "mux cold attach saturated" in message
        or "no page found" in message
        or "response timed out" in message
        or "thread join timed out" in message
        or "e2e_signoff_new_page_join_stall" in message
        or "wall budget exhausted" in message
        or "transport closed" in message
        or "transport dead" in message
        or "connection reset" in message
        or "could not connect to chrome" in message
        or "unexpected server response: 404" in message
        or "cdp endpoint not ready" in message
        or "cdp/mux endpoint not ready" in message
        or "shpoib runtime rebind after reload failed" in message
    )


def _sync_open_page_tool_wall(
    client: ChromeMcpClient,
    *,
    wall_deadline: float,
    total_deadline: float,
    steps_remaining: int,
    floor_sec: float = 90.0,
) -> None:
    """Refresh per-step tool wall budget so SHPOIB multi-hop open does not exhaust early (R118)."""
    now = time.monotonic()
    remaining = min(wall_deadline, total_deadline) - now
    if remaining <= 0:
        if is_e2e_signoff_runtime():
            return
        client.set_tool_wall_deadline(now)
        return
    if _open_page_parallel_total_wall_only():
        client.set_tool_wall_deadline(total_deadline)
        return
    parallel_peers = _parallel_open_page_peer_count()
    if parallel_peers >= 2:
        floor_sec = max(floor_sec, min(120.0 + parallel_peers * 8.0, 180.0))
    if parallel_peers >= 4:
        client.set_tool_wall_deadline(now + min(remaining, 180.0))
        return
    slice_sec = max(floor_sec, remaining / max(1, steps_remaining))
    client.set_tool_wall_deadline(now + min(remaining, slice_sec))


def _refresh_signoff_open_nav_tool_wall(
    client: ChromeMcpClient,
    *,
    wall_deadline: float,
    total_deadline: float,
) -> None:
    """R213: refresh tool wall after mux/new_page gate consumed attempt-local remaining."""
    if not is_e2e_signoff_runtime():
        return
    from dev_gate_contract import signoff_open_mcp_budgets

    now = time.monotonic()
    peers = _parallel_open_page_peer_count()
    budgets = signoff_open_mcp_budgets(parallel_peers=peers)
    attempt_remaining = min(
        max(0.0, wall_deadline - now),
        max(0.0, total_deadline - now),
    )
    bootstrap_remaining = attempt_remaining
    try:
        from e2e_session_lifecycle import current_phase, remaining_wall_sec

        if current_phase() == "bootstrap":
            bootstrap_remaining = max(attempt_remaining, remaining_wall_sec())
    except ImportError:
        pass
    nav_floor = min(float(budgets.layout_wait_sec), budgets.wall_budget_sec * 0.6)
    if peers >= 2:
        nav_floor = max(nav_floor, 90.0 + peers * 12.0)
    if attempt_remaining < 30.0 and bootstrap_remaining < 30.0:
        # R265: mux queue consumed attempt wall — grant fresh nav slice from SSOT.
        budget = max(
            nav_floor, float(budgets.layout_wait_sec), budgets.wall_budget_sec * 0.55
        )
    else:
        budget = max(nav_floor, min(bootstrap_remaining, budgets.wall_budget_sec))
    client.set_tool_wall_deadline(now + budget)


def _require_orchestrator_for_formal_e2e() -> None:
    lane = os.environ.get("MYRM_E2E_LANE", "").strip()
    if not lane:
        return
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        return
    from dev_gate_contract import BROWSER_ORCHESTRATOR_REQUIRED_TOKEN  # noqa: PLC0415

    raise RuntimeError(
        f"{BROWSER_ORCHESTRATOR_REQUIRED_TOKEN}: formal chrome_e2e requires "
        "MYRM_BROWSER_ORCHESTRATOR=1 — launch via ./myrm test, not raw pytest/mux"
    )


@contextmanager
def open_mcp_page(
    url: str,
    *,
    timeout_ms: int | None = None,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    _require_orchestrator_for_formal_e2e()
    resolved_timeout_ms = timeout_ms if timeout_ms is not None else 90_000
    if is_e2e_signoff_runtime():
        resolved_timeout_ms = min(resolved_timeout_ms, 90_000)
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        from browser_orchestrator_e2e import open_orchestrator_mcp_page

        with open_orchestrator_mcp_page(
            url,
            request_timeout_sec=request_timeout_sec,
        ) as (client, page):
            yield client, page  # type: ignore[misc]
        return
    from dev_gate_contract import BROWSER_ORCHESTRATOR_REQUIRED_TOKEN

    raise RuntimeError(
        f"{BROWSER_ORCHESTRATOR_REQUIRED_TOKEN}: Dev Gate chrome_e2e requires "
        "MYRM_BROWSER_ORCHESTRATOR=1 — launch via ./myrm test -m chrome_e2e"
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


def _coerce_evaluate_result(raw: object) -> dict[str, object]:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        stripped = raw.strip()
        if stripped.startswith("{"):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass
    return {"value": raw}


_REACT_E2E_BRIDGE_PROBE_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function'
    && window.__MYRM_E2E_CHAT__?.__e2eFallback !== true,
  hasAttach: typeof window.__MYRM_E2E_CHAT__?.attachToChat === 'function',
  fallback: window.__MYRM_E2E_CHAT__?.__e2eFallback === true,
  hasInput: Boolean(document.querySelector('[data-chat-input]')),
  hasAppLayout: Boolean(document.querySelector('[data-testid="app-layout"]')),
  hasSkeleton: Boolean(document.querySelector('[data-testid="app-shell-skeleton"]')),
  bodyLength: (document.body?.innerText || '').length,
  href: location.href,
}))()"""

_ATTACH_CLIENT_WARMUP_TRIGGERED = False
_ATTACH_CLIENT_WARMUP_URL: str | None = None
_ATTACH_FRONTEND_HEAL_TRIGGERED = False


def _trigger_attach_frontend_heal_once() -> None:
    """Restart Turbopack when HTTP 200 shell persists without client hydration (R284 body SSOT)."""
    global _ATTACH_CLIENT_WARMUP_TRIGGERED, _ATTACH_FRONTEND_HEAL_TRIGGERED
    if _ATTACH_FRONTEND_HEAL_TRIGGERED:
        return
    _ATTACH_FRONTEND_HEAL_TRIGGERED = True
    monorepo_root = Path(__file__).resolve().parents[4]
    try:
        from e2e_warm_ui_heal import heal_shared_frontend_attach

        touch_wall_progress(current_node="attach_frontend_heal")
        heal_shared_frontend_attach(monorepo_root)
        _ATTACH_CLIENT_WARMUP_TRIGGERED = False
    except ImportError:
        pass


def _trigger_attach_client_warmup_once(*, page_url: str | None = None) -> None:
    """Run global CDP client hydration once when attach ADMIT skipped clientHot (R284 body SSOT)."""
    import subprocess

    global _ATTACH_CLIENT_WARMUP_TRIGGERED, _ATTACH_CLIENT_WARMUP_URL
    ui = (page_url or f"{get_e2e_ui_url().rstrip('/')}/").rstrip("/") + "/"
    if _ATTACH_CLIENT_WARMUP_TRIGGERED and _ATTACH_CLIENT_WARMUP_URL == ui:
        return
    _ATTACH_CLIENT_WARMUP_TRIGGERED = True
    _ATTACH_CLIENT_WARMUP_URL = ui
    monorepo_root = Path(__file__).resolve().parents[4]
    warmup_py = monorepo_root / "myrm-agent/scripts/dev/lib/frontend-client-warmup.py"
    if not warmup_py.is_file():
        return
    server_root = Path(__file__).resolve().parents[1]
    venv_py = server_root / ".venv/bin/python"
    py = str(venv_py) if venv_py.is_file() else sys.executable
    cdp_port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
    touch_wall_progress(current_node="attach_client_warmup")
    try:
        subprocess.run(
            [
                py,
                str(warmup_py),
                "--cdp-port",
                str(cdp_port),
                "--url",
                ui,
                "--timeout-sec",
                "90",
            ],
            timeout=120.0,
            check=False,
            capture_output=True,
            cwd=str(server_root),
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


def _react_bridge_wait_timeout_sec(requested: float) -> float:
    try:
        from e2e_shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return min(max(requested, 90.0), 180.0)
    except ImportError:
        pass
    return min(max(requested, 60.0), 120.0)


def wait_for_react_e2e_bridge(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 90.0,
    page_url: str | None = None,
) -> dict[str, object]:
    """Wait for full React E2E bridge (attachToChat); reload-heal when clientHot was skipped at ADMIT."""
    target_url = page_url or getattr(page, "url", None)
    _trigger_attach_client_warmup_once(
        page_url=target_url if isinstance(target_url, str) else None
    )
    deadline = time.monotonic() + _react_bridge_wait_timeout_sec(timeout_sec)
    last: dict[str, object] = {}
    polls = 0
    reload_passes = 0
    max_reload_passes = 3
    ui_home = f"{get_e2e_ui_url().rstrip('/')}/"

    while time.monotonic() < deadline:
        polls += 1
        touch_wall_progress(current_node="wait_for_react_e2e_bridge")
        raw = client.evaluate(
            page,
            _REACT_E2E_BRIDGE_PROBE_JS,
            timeout_sec=max(5.0, min(30.0, deadline - time.monotonic())),
        )
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return last
        body_length = last.get("bodyLength")
        href = str(last.get("href", ""))
        if (
            isinstance(body_length, int)
            and body_length < 20
            and polls in {1, 4, 8}
            and ("127.0.0.1" in href or "localhost" in href)
        ):
            from urllib.parse import urlparse

            warm_path = urlparse(href).path or "/"
            try:
                warm_ui_route(warm_path, timeout_sec=60.0)
            except RuntimeError:
                pass
            _trigger_attach_frontend_heal_once()
        if (
            isinstance(body_length, int)
            and body_length < 20
            and polls >= 3
            and isinstance(target_url, str)
            and reload_passes < max_reload_passes
        ):
            reload_passes += 1
            reload_mcp_page(client, page, target_url=target_url, timeout_ms=120_000)
            try:
                dismiss_blocking_modals(client, page)
            except AssertionError:
                pass
            time.sleep(2.0)
            continue
        if (
            last.get("hasAppLayout") is True
            and last.get("hasInput") is True
            and last.get("fallback") is not True
            and polls >= 8
        ):
            return {**last, "ready": True, "softReady": True}
        if (
            last.get("hasSkeleton") is True
            or (last.get("hasAppLayout") is True and last.get("hasAttach") is not True)
        ) and polls in {6, 18, 36, 54}:
            _trigger_attach_frontend_heal_once()
            _trigger_attach_client_warmup_once(
                page_url=target_url if isinstance(target_url, str) else None
            )
            try:
                dismiss_blocking_modals(client, page)
            except AssertionError:
                pass
            if isinstance(target_url, str) and reload_passes < max_reload_passes:
                reload_passes += 1
                reload_mcp_page(client, page, target_url=target_url, timeout_ms=120_000)
                time.sleep(2.0)
                continue
        should_home_heal = (
            last.get("hasInput") is not True
            and polls in {8, 24, 48, 72}
            and isinstance(target_url, str)
        )
        if should_home_heal and reload_passes < max_reload_passes:
            reload_passes += 1
            client.navigate(page, ui_home)
            time.sleep(3.0)
            dismiss_blocking_modals(client, page)
            client.navigate(page, target_url)
            time.sleep(2.0)
            dismiss_blocking_modals(client, page)
            continue
        should_reload = last.get("fallback") is True or (
            polls in {20, 40, 60, 80} and last.get("hasAttach") is not True
        )
        if (
            should_reload
            and reload_passes < max_reload_passes
            and isinstance(target_url, str)
        ):
            reload_passes += 1
            reload_mcp_page(client, page, target_url=target_url, timeout_ms=120_000)
            dismiss_blocking_modals(client, page)
            time.sleep(2.0)
            continue
        time.sleep(0.5)

    raise AssertionError(f"React E2E bridge did not become ready: {last}")


def _state_looks_blank(last: dict[str, object]) -> bool:
    body_len = last.get("bodyLength")
    if body_len is not None and int(body_len or 0) == 0:
        return True
    if last.get("hasActiveSection") is False and int(last.get("matrixHits") or 0) == 0:
        heading = str(last.get("heading") or "")
        relay = str(last.get("relayLine") or "")
        if not heading and not relay and last.get("pathname"):
            return True
    pathname = str(last.get("pathname") or "")
    if pathname in {"", "/"} or "blank" in pathname.lower():
        return True
    return False


def _looks_like_cdp_transport_error(message: str) -> bool:
    lowered = message.lower()
    return (
        "browser orchestrator error" in lowered
        or "browser orchestrator response timeout" in lowered
        or "operation queue timeout" in lowered
        or "operation timeout:" in lowered
        or "cdp request timeout" in lowered
        or "cdp not connected" in lowered
        or "cdp connection closed" in lowered
        or "cdp websocket closed" in lowered
        or "no target with given id" in lowered
        or "connection reset" in lowered
        or "broken pipe" in lowered
    )


def wait_for_state(
    client: ChromeMcpClient,
    page: McpPage,
    expression: str,
    *,
    timeout_sec: float = 45.0,
    page_url: str | None = None,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    last_touch = 0.0
    polls = 0
    reload_passes = 0
    max_reload_passes = 3
    transport_streak = 0
    ui_home = f"{get_e2e_ui_url().rstrip('/')}/"

    while time.monotonic() < deadline:
        polls += 1
        remaining = max(0.0, deadline - time.monotonic())
        now = time.monotonic()
        if now - last_touch >= 5.0:
            touch_wall_progress(current_node="wait_for_state")
            last_touch = now
        eval_cap = 60.0
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
        if (
            page_url
            and reload_passes < max_reload_passes
            and polls in {16, 48, 96, 160}
            and _state_looks_blank(last)
        ):
            reload_passes += 1
            touch_wall_progress(current_node="wait_for_state_blank_heal")
            try:
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
                reload_mcp_page(client, page, target_url=page_url, timeout_ms=120_000)
                dismiss_blocking_modals(client, page)
            continue
        time.sleep(0.25)
    raise AssertionError(f"Browser state did not become ready: {last}")
