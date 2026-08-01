"""Shared real-Chrome MCP helpers for formal UI E2E tests."""

from __future__ import annotations

import asyncio
import json
import os
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


def dismiss_blocking_modals(client: ChromeMcpClient, page: McpPage) -> None:
    """Dismiss onboarding/migration overlays that block E2E clicks (SSOT: cdp_chat_support)."""
    wait_for_state(client, page, _LOCALHOST_PAGE_JS, timeout_sec=45.0)
    dismissed = client.evaluate(page, DISMISS_MODALS_JS, timeout_sec=10.0)
    assert isinstance(dismissed, dict) and dismissed.get("ok") is True, dismissed
    boot = client.evaluate(
        page,
        """(() => {
          try { localStorage.setItem('myrm_boot_shown', '1'); } catch (err) {
            return { ok: false, err: String(err) };
          }
          return { ok: true };
        })()""",
        timeout_sec=5.0,
    )
    assert isinstance(boot, dict) and boot.get("ok") is True, boot


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
    allowed = (get_e2e_ui_url(), get_e2e_api_url())
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
    monorepo_root = Path(__file__).resolve().parents[4]
    try:
        from dev_gate_contract import shared_ui_hydrate_wait_sec
        from stack_mutation_policy import wave_active_lease_count
        from transport_supervisor import parallel_active_test_count

        active = max(
            wave_active_lease_count(monorepo_root),
            parallel_active_test_count(),
        )
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

    def _warm_ui_poll_loop() -> None:
        nonlocal last_error, next_heal_at
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            touch_wall_progress(current_node="warm_ui_route")
            if time.monotonic() >= next_heal_at:
                next_heal_at = time.monotonic() + heal_interval
                _heal_shared_frontend()
            request = urllib.request.Request(  # noqa: S310 - loopback only
                url, method="GET"
            )
            per_attempt = max(3.0, min(10.0, deadline - time.monotonic()))
            try:
                with urllib.request.urlopen(  # noqa: S310
                    request, timeout=per_attempt
                ) as response:
                    if response.status == 200:
                        return
                    last_error = RuntimeError(
                        f"warm_ui_route GET {url} returned HTTP {response.status}"
                    )
                    if response.status in {404, 502, 503}:
                        _heal_shared_frontend()
                        next_heal_at = time.monotonic() + heal_interval
            except urllib.error.HTTPError as exc:
                # Next.js cold compile often returns 404 before routes are ready.
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

    # R148: SHPOIB parallel must serialize shared :3000 compile bursts (same flock as navigate).
    if parallel_shared_ui_hydrate_queue_enabled():
        with shared_ui_hydrate_slot():
            _warm_ui_poll_loop()
    else:
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
    if bootstrap_js is None:
        raise RuntimeError("SHPOIB bootstrap JS missing after reload")
    if is_e2e_signoff_runtime():
        timeout_sec = max(timeout_sec, float(SIGNOFF_SHPOIB_REBIND_WALL_SEC))
    parallel_peers = _parallel_open_page_peer_count()
    if parallel_peers >= 2:
        rebind_cap = 420.0 if is_e2e_signoff_runtime() else 300.0
        timeout_sec = min(timeout_sec + parallel_peers * 15.0, rebind_cap)
    deadline = time.monotonic() + timeout_sec
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
        normalized_target = _normalize_rebind_target_url(target_url)
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
    if is_e2e_signoff_runtime():
        return float(SIGNOFF_OPEN_PAGE_LAYOUT_WAIT_SEC)
    return _OPEN_PAGE_LAYOUT_WAIT_SEC


def _shpoib_rebind_location_wait_cap() -> float:
    return shpoib_rebind_location_wait_cap_sec()


def _open_page_parallel_retry_allowed() -> bool:
    """Signoff and dev PRIVATE SHPOIB bootstrap share mux-heal retry under parallel peers."""
    return is_e2e_signoff_runtime() or _dev_private_shpoib_bootstrap_phase()


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
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load()
        mux = int(load.mux_contexts)
        wave = int(load.wave_leases)
        if is_e2e_signoff_runtime():
            # R184: parent signoff runner leaves stale wave leases — mux contexts is ground truth.
            return mux if mux > 0 else wave
        return max(wave, mux)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    monorepo_root = Path(__file__).resolve().parents[4]
    try:
        from stack_mutation_policy import wave_active_lease_count

        return wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


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


def _signoff_wait_mux_before_new_page(*, budget_sec: float | None = None) -> None:
    """Signoff pre-new_page mux gate — operation-credit transport SSOT (P0-B)."""
    from browser_orchestrator import wait_for_operation_credit

    wait_budget = float(
        budget_sec if budget_sec is not None else _signoff_mux_drain_budget_sec()
    )
    wait_for_operation_credit(
        budget_sec=wait_budget,
        current_node="open_mcp_page_signoff_gate",
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
        worker.join(
            timeout=min(poll_sec, join_deadline - now, stall_deadline - now)
        )
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
    budget = max(nav_floor, min(bootstrap_remaining, budgets.wall_budget_sec))
    client.set_tool_wall_deadline(now + budget)


@contextmanager
def open_mcp_page(
    url: str,
    *,
    timeout_ms: int | None = None,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    shpoib_active = e2e_runtime_binding() is not None
    resolved_timeout_ms = timeout_ms if timeout_ms is not None else 90_000
    if is_e2e_signoff_runtime():
        resolved_timeout_ms = min(resolved_timeout_ms, 90_000)
    new_page_timeout_ms = min(resolved_timeout_ms, _OPEN_PAGE_NEW_PAGE_TIMEOUT_MS)
    (
        client_timeout_sec,
        new_page_timeout_ms,
        open_page_wall_budget_sec,
        open_page_total_budget_sec,
        open_page_attempts,
    ) = _open_page_parallel_budgets(
        request_timeout_sec,
        new_page_timeout_ms=new_page_timeout_ms,
    )
    heartbeat_e2e_lease()
    touch_wall_progress(current_node="open_mcp_page_attempt")
    parallel_transport = _open_page_parallel_total_wall_only()
    boot_mux_gate_ok = os.environ.get("MYRM_E2E_BOOT_MUX_GATE_OK", "").strip() == "1"
    if _parallel_open_page_peer_count() >= 2:
        from browser_orchestrator import wait_for_operation_credit
        from transport_supervisor import mux_upstream_wait_cap

        if boot_mux_gate_ok:
            probe_budget = (
                _signoff_mux_drain_budget_sec() if is_e2e_signoff_runtime() else 15.0
            )
            probe_budget = min(probe_budget, 45.0)
        else:
            probe_budget = float(mux_upstream_wait_cap())
        wait_for_operation_credit(
            budget_sec=probe_budget,
            current_node="open_mcp_page_boot_gate",
        )
    transport_session_started = time.monotonic()
    total_deadline = transport_session_started + open_page_total_budget_sec
    wall_deadline = transport_session_started + open_page_wall_budget_sec
    last_exc: BaseException | None = None
    mux_restarted = False
    if is_e2e_signoff_runtime():
        _force_mux_attach_restart_after_new_page_timeout()
        try:
            ChromeMcpClient(
                request_timeout_sec=client_timeout_sec
            ).recover_mux_transport()
        except RuntimeError:
            pass
        try:
            _signoff_wait_mux_before_new_page()
        except RuntimeError:
            pass
        time.sleep(2.0)
    for attempt in range(open_page_attempts):
        if is_e2e_signoff_runtime() and attempt > 0:
            _force_mux_attach_restart_after_new_page_timeout()
            transport_session_started, wall_deadline, total_deadline = (
                _restart_open_page_mux_budget(
                    open_page_wall_budget_sec=open_page_wall_budget_sec,
                    open_page_total_budget_sec=open_page_total_budget_sec,
                )
            )
            mux_restarted = False
            touch_wall_progress(current_node="open_mcp_page_signoff_retry")
            try:
                _signoff_wait_mux_before_new_page(
                    budget_sec=max(30.0, _signoff_mux_drain_budget_sec() * 0.5)
                )
            except RuntimeError:
                pass
            time.sleep(2.0)
        if time.monotonic() >= total_deadline:
            signoff_budget_retry = (
                is_e2e_signoff_runtime()
                and attempt < open_page_attempts - 1
                and _open_page_allow_mux_budget_extension()
            )
            if signoff_budget_retry:
                if last_exc is None:
                    last_exc = RuntimeError(
                        f"{MUX_RECLAIM_STALL_TOKEN}: open_mcp_page total budget "
                        f"{open_page_total_budget_sec:.0f}s exhausted on attempt {attempt + 1}"
                    )
                transport_session_started, wall_deadline, total_deadline = (
                    _restart_open_page_mux_budget(
                        open_page_wall_budget_sec=open_page_wall_budget_sec,
                        open_page_total_budget_sec=open_page_total_budget_sec,
                    )
                )
                mux_restarted = False
                continue
            if (
                _open_page_allow_mux_budget_extension()
                and not mux_restarted
                and last_exc is not None
            ):
                transport_session_started, wall_deadline, total_deadline = (
                    _restart_open_page_mux_budget(
                        open_page_wall_budget_sec=open_page_wall_budget_sec,
                        open_page_total_budget_sec=open_page_total_budget_sec,
                    )
                )
                mux_restarted = True
                continue
            raise RuntimeError(
                f"open_mcp_page total budget {open_page_total_budget_sec:.0f}s exhausted "
                f"after {attempt} attempt(s): {last_exc!r}"
            )
        if time.monotonic() >= wall_deadline:
            if (
                _open_page_allow_mux_budget_extension()
                and not mux_restarted
                and last_exc is not None
                and _retryable_open_page_error(last_exc)
            ):
                _force_mux_attach_restart_after_new_page_timeout()
                mux_restarted = True
                wall_deadline = time.monotonic() + open_page_wall_budget_sec
                total_deadline = time.monotonic() + open_page_total_budget_sec
                continue
        heartbeat_e2e_lease()
        touch_wall_progress(current_node="open_mcp_page_attempt")
        if _parallel_open_page_peer_count() >= 2:
            from browser_orchestrator import wait_for_operation_credit

            wait_for_operation_credit(budget_sec=_mux_transport_wait_budget_sec())
        attempt_mono = time.monotonic()
        attempt_wall_deadline = attempt_mono + open_page_wall_budget_sec
        attempt_total_deadline = attempt_mono + open_page_total_budget_sec
        client = ChromeMcpClient(request_timeout_sec=client_timeout_sec)
        try:
            with _blocking_progress_loop(
                current_node="open_mcp_page_blocking",
                transport_session_started=transport_session_started,
            ):
                heartbeat_e2e_lease()
                touch_wall_progress(current_node="open_mcp_page_blocking")
                _require_e2e_cdp_ready()
                wall_deadline = attempt_wall_deadline
                total_deadline = attempt_total_deadline
                client.start()
                # R184: signoff SHPOIB — client.new_page injects runtime binding; skip duplicate blank→nav.
                if is_e2e_signoff_runtime():
                    shpoib_blank_nav = False
                else:
                    shpoib_blank_nav = (
                        shpoib_active and _parallel_open_page_peer_count() < 2
                    )
                open_steps = 4 if shpoib_blank_nav else 2
                if shpoib_blank_nav:
                    client.set_tool_wall_deadline(None)
                    page = _open_page_new_page(
                        client,
                        "about:blank",
                        timeout_ms=new_page_timeout_ms,
                        attempt_wall_deadline=attempt_wall_deadline,
                    )
                    ensure_desktop_viewport(client, page)
                    open_steps -= 1
                    _sync_open_page_tool_wall(
                        client,
                        wall_deadline=wall_deadline,
                        total_deadline=total_deadline,
                        steps_remaining=open_steps,
                    )
                    binding_source = e2e_runtime_binding_source()
                    if binding_source:
                        # R156: runtime inject must not share sliced tool wall under parallel mux.
                        client.set_tool_wall_deadline(None)
                        client.evaluate(
                            page,
                            f"(() => {{{binding_source} return true; }})()",
                        )
                        _sync_open_page_tool_wall(
                            client,
                            wall_deadline=wall_deadline,
                            total_deadline=total_deadline,
                            steps_remaining=open_steps,
                        )
                    client.navigate(page, url, timeout_ms=resolved_timeout_ms)
                    open_steps -= 1
                    _sync_open_page_tool_wall(
                        client,
                        wall_deadline=wall_deadline,
                        total_deadline=total_deadline,
                        steps_remaining=open_steps,
                    )
                    _reapply_shpoib_runtime_after_reload(client, page, target_url=url)
                    open_steps -= 1
                else:
                    page = _open_page_new_page(
                        client,
                        url,
                        timeout_ms=new_page_timeout_ms,
                        attempt_wall_deadline=attempt_wall_deadline,
                    )
                    ensure_desktop_viewport(client, page)
                    open_steps -= 1
                open_steps -= 1
                _sync_open_page_tool_wall(
                    client,
                    wall_deadline=wall_deadline,
                    total_deadline=total_deadline,
                    steps_remaining=max(1, open_steps),
                )
                _refresh_signoff_open_nav_tool_wall(
                    client,
                    wall_deadline=wall_deadline,
                    total_deadline=total_deadline,
                )
                if (
                    _parallel_open_page_peer_count() >= 2
                    and not is_e2e_signoff_runtime()
                ):
                    # R171: layout poll must not inherit sliced evaluate wall under mux queue.
                    client.set_tool_wall_deadline(None)
                wait_for_state(
                    client,
                    page,
                    """(() => ({
                      ready: !!document.querySelector('[data-testid="app-layout"]'),
                    }))()""",
                    timeout_sec=_open_page_layout_wait_sec(),
                )
                client.set_tool_wall_deadline(None)
            from e2e_session_lifecycle import current_phase, seal_page_open_body_budget

            if current_phase() == "bootstrap":
                seal_page_open_body_budget(phase_label="open_mcp_page")
            try:
                yield client, page
            finally:
                client.close()
            return
        except KeyboardInterrupt:
            last_exc = RuntimeError(
                f"{MUX_RECLAIM_STALL_TOKEN}: open_mcp_page transport stall tripwire"
            )
            try:
                client.abandon_inflight_requests(cdp_drift=True)
            except RuntimeError:
                pass
            try:
                client.close()
            except RuntimeError:
                pass
            if attempt >= open_page_attempts - 1:
                raise last_exc from None
            if is_e2e_signoff_runtime() and attempt + 1 < open_page_attempts:
                transport_session_started, wall_deadline, total_deadline = (
                    _restart_open_page_mux_budget(
                        open_page_wall_budget_sec=open_page_wall_budget_sec,
                        open_page_total_budget_sec=open_page_total_budget_sec,
                    )
                )
                mux_restarted = False
                touch_wall_progress(current_node="open_mcp_page_mux_retry")
            elif _open_page_allow_mux_budget_extension():
                if not mux_restarted:
                    _force_mux_attach_restart_after_new_page_timeout()
                    mux_restarted = True
                try:
                    ChromeMcpClient(
                        request_timeout_sec=client_timeout_sec
                    ).recover_mux_transport()
                except RuntimeError:
                    pass
                _require_e2e_cdp_ready(budget_sec=30.0)
                wall_deadline = time.monotonic() + open_page_wall_budget_sec
                total_deadline = time.monotonic() + open_page_total_budget_sec
                time.sleep(5.0)
                try:
                    _wait_mux_cold_attach_drain(
                        budget_sec=_mux_cold_attach_drain_budget_sec()
                    )
                except RuntimeError:
                    pass
            time.sleep(3.0 * (attempt + 1))
            continue
        except (RuntimeError, TimeoutError) as exc:
            last_exc = exc
            exc_message = str(exc).lower()
            cdp_drift = (
                "could not connect to chrome" in exc_message
                or "unexpected server response: 404" in exc_message
            )
            try:
                client.abandon_inflight_requests(cdp_drift=cdp_drift)
            except RuntimeError:
                pass
            try:
                client.close()
            except RuntimeError:
                pass
            if (
                isinstance(exc, TimeoutError)
                or MUX_RECLAIM_STALL_TOKEN.lower() in exc_message
                or "not owned by this shim" in exc_message
                or "response timed out" in exc_message
                or "wall budget exhausted" in exc_message
                or "connection reset" in exc_message
                or "could not connect to chrome" in exc_message
                or "unexpected server response: 404" in exc_message
                or "cdp/mux endpoint not ready" in exc_message
                or "cdp endpoint not ready" in exc_message
            ):
                if (
                    _open_page_allow_mux_budget_extension()
                    or _open_page_parallel_retry_allowed()
                ):
                    if not mux_restarted and _open_page_parallel_retry_allowed():
                        transport_session_started, wall_deadline, total_deadline = (
                            _restart_open_page_mux_budget(
                                open_page_wall_budget_sec=open_page_wall_budget_sec,
                                open_page_total_budget_sec=open_page_total_budget_sec,
                            )
                        )
                        mux_restarted = True
                    elif not mux_restarted:
                        _force_mux_attach_restart_after_new_page_timeout()
                        mux_restarted = True
                    try:
                        ChromeMcpClient(
                            request_timeout_sec=client_timeout_sec
                        ).recover_mux_transport()
                    except RuntimeError:
                        pass
                    _require_e2e_cdp_ready(budget_sec=30.0)
                    wall_deadline = time.monotonic() + open_page_wall_budget_sec
                    total_deadline = time.monotonic() + open_page_total_budget_sec
                    time.sleep(5.0)
                    try:
                        _wait_mux_cold_attach_drain(
                            budget_sec=_mux_cold_attach_drain_budget_sec()
                        )
                    except RuntimeError:
                        pass
                else:
                    try:
                        ChromeMcpClient(
                            request_timeout_sec=client_timeout_sec
                        ).recover_mux_transport()
                    except RuntimeError:
                        pass
            if parallel_transport and not (
                _open_page_parallel_retry_allowed()
                and _retryable_open_page_error(exc)
                and attempt < open_page_attempts - 1
            ):
                raise
            if attempt >= open_page_attempts - 1 or not _retryable_open_page_error(exc):
                raise
            if _open_page_parallel_retry_allowed() and attempt + 1 < open_page_attempts:
                transport_session_started, wall_deadline, total_deadline = (
                    _restart_open_page_mux_budget(
                        open_page_wall_budget_sec=open_page_wall_budget_sec,
                        open_page_total_budget_sec=open_page_total_budget_sec,
                    )
                )
                mux_restarted = False
            time.sleep(3.0 * (attempt + 1))
            continue
    raise last_exc or RuntimeError("open_mcp_page failed without exception")


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


def wait_for_state(
    client: ChromeMcpClient,
    page: McpPage,
    expression: str,
    *,
    timeout_sec: float = 45.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        remaining = max(0.0, deadline - time.monotonic())
        touch_wall_progress(current_node="wait_for_state")
        raw = client.evaluate(
            page,
            expression,
            timeout_sec=max(5.0, min(30.0, remaining)),
        )
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return last
        time.sleep(0.25)
    raise AssertionError(f"Browser state did not become ready: {last}")
