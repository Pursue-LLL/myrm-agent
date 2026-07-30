"""Shared real-Chrome MCP helpers for formal UI E2E tests."""

from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
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
    SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC,
    SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC,
    SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC,
    SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC,
    SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC,
    SIGNOFF_SHPOIB_REBIND_WALL_SEC,
    is_e2e_signoff_runtime,
)  # noqa: E402
from e2e_orchestrator import touch_wall_progress  # noqa: E402
from e2e_shared_ui_hydrate import (  # noqa: E402
    parallel_shared_ui_hydrate_queue_enabled,
    shared_ui_hydrate_slot,
)
from e2e_warm_ui_heal import heal_shared_frontend_debounced  # noqa: E402
from mux_upstream_admission import (  # noqa: E402
    read_mux_cold_attach_status,
    wait_mux_hand_probe_allowed,
)

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
    "http_json",
    "open_mcp_page",
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
    """Mark onboarding complete so PageLayout does not overlay the chat during E2E."""
    http_json(
        "POST",
        f"{api_url}/api/v1/config/onboarding/complete",
        expected_statuses=frozenset({200, 201}),
    )


def http_json(
    method: str,
    url: str,
    body: dict[str, object] | None = None,
    *,
    expected_statuses: frozenset[int] = frozenset({200, 201, 204}),
) -> object:
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
            request, timeout_sec=30.0
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
    """Extend warm budget when wave leases contend for shared Next compile (R120)."""
    monorepo_root = Path(__file__).resolve().parents[4]
    try:
        from dev_gate_contract import shared_ui_hydrate_wait_sec
        from stack_mutation_policy import wave_active_lease_count

        active = wave_active_lease_count(monorepo_root)
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

    from e2e_stall_guard import assert_transport_node_not_stuck, transport_stall_cap_sec

    stop = threading.Event()
    node_started = (
        transport_session_started
        if transport_session_started is not None
        else time.monotonic()
    )
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
    stall_cap = max(transport_stall_cap_sec(), open_page_total_budget + 15.0)
    if _parallel_open_page_peer_count() >= 2:
        stall_cap = min(
            transport_stall_cap_sec(),
            _open_page_body_fraction_cap_sec(),
        )

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
                return
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
    if is_e2e_signoff_runtime():
        return float(SIGNOFF_SHPOIB_REBIND_LOCATION_WAIT_SEC)
    return 45.0


def _open_page_attempt_count() -> int:
    """R152 TPMc: parallel mux — single outer pass; no retry that resets session clock."""
    if _parallel_open_page_peer_count() >= 2:
        return 1
    return _OPEN_PAGE_ATTEMPTS


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
    wall_budget = (
        float(SIGNOFF_OPEN_PAGE_WALL_BUDGET_SEC)
        if signoff
        else _OPEN_PAGE_WALL_BUDGET_SEC
    )
    total_budget = (
        float(SIGNOFF_OPEN_PAGE_TOTAL_BUDGET_SEC)
        if signoff
        else _OPEN_PAGE_TOTAL_BUDGET_SEC
    )
    wall_cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_WALL_CAP_SEC) if signoff else 300.0
    total_cap = float(SIGNOFF_OPEN_PAGE_PARALLEL_TOTAL_CAP_SEC) if signoff else 480.0
    parallel_peers = _parallel_open_page_peer_count()
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
        _open_page_attempt_count(),
    )


def _parallel_open_page_peer_count() -> int:
    """Wave/mux peers for open_mcp_page heal policy (R122-B8)."""
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load()
        return max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        pass
    monorepo_root = Path(__file__).resolve().parents[4]
    try:
        from stack_mutation_policy import wave_active_lease_count

        return wave_active_lease_count(monorepo_root)
    except (ImportError, OSError, RuntimeError, ValueError):
        return 0


def _should_skip_attach_preflight_restart() -> bool:
    """R122-B8: full attach-restart preflight waits UI under parallel — use shim recover."""
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


def _wait_mux_cold_attach_drain(*, budget_sec: float) -> None:
    """Wait until no other mux cold-attach ops hold registry slots (post-timeout heal)."""
    deadline = time.monotonic() + budget_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        touch_wall_progress(current_node="open_mcp_page_mux_drain")
        last = read_mux_cold_attach_status()
        if int(last.get("active") or 0) == 0:
            return
        time.sleep(2.0)
    raise RuntimeError(
        f"MUX cold attach drain timeout after {budget_sec:.0f}s: active={last.get('active')!r}"
    )


def _retryable_open_page_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        MUX_RECLAIM_STALL_TOKEN.lower() in message
        or "mux cold attach saturated" in message
        or "no page found" in message
        or "response timed out" in message
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


@contextmanager
def open_mcp_page(
    url: str,
    *,
    timeout_ms: int | None = None,
    request_timeout_sec: float = 180.0,
) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    shpoib_active = e2e_runtime_binding() is not None
    resolved_timeout_ms = timeout_ms if timeout_ms is not None else 90_000
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
        if boot_mux_gate_ok:
            # R155: BOOT gate already waited — short BODY sanity only.
            wait_mux_hand_probe_allowed(budget_sec=15.0)
        else:
            from transport_supervisor import mux_upstream_wait_cap

            probe_budget = float(mux_upstream_wait_cap())
            wait_mux_hand_probe_allowed(budget_sec=probe_budget)
            # R154: drain mux cold-attach slots before BODY transport pass (not mid-retry).
            try:
                _wait_mux_cold_attach_drain(budget_sec=min(60.0, probe_budget))
            except RuntimeError as drain_exc:
                if parallel_transport:
                    raise RuntimeError(
                        f"E2E_MUX_PRE_BODY_BACKPRESSURE: {drain_exc}"
                    ) from drain_exc
                raise
    transport_session_started = time.monotonic()
    total_deadline = transport_session_started + open_page_total_budget_sec
    wall_deadline = transport_session_started + open_page_wall_budget_sec
    last_exc: BaseException | None = None
    mux_restarted = False
    for attempt in range(open_page_attempts):
        if time.monotonic() >= total_deadline:
            if (
                _open_page_allow_mux_budget_extension()
                and not mux_restarted
                and last_exc is not None
            ):
                _force_mux_attach_restart_after_new_page_timeout()
                mux_restarted = True
                total_deadline = time.monotonic() + open_page_total_budget_sec
                wall_deadline = time.monotonic() + open_page_wall_budget_sec
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
        client = ChromeMcpClient(request_timeout_sec=client_timeout_sec)
        try:
            with _blocking_progress_loop(
                current_node="open_mcp_page_blocking",
                transport_session_started=transport_session_started,
            ):
                heartbeat_e2e_lease()
                touch_wall_progress(current_node="open_mcp_page_blocking")
                _require_e2e_cdp_ready()
                wall_deadline = time.monotonic() + open_page_wall_budget_sec
                total_deadline = time.monotonic() + open_page_total_budget_sec
                client.start()
                open_steps = 4 if shpoib_active else 2
                if shpoib_active:
                    client.set_tool_wall_deadline(None)
                    page = client.new_page(
                        "about:blank", timeout_ms=new_page_timeout_ms
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
                    page = client.new_page(url, timeout_ms=new_page_timeout_ms)
                    ensure_desktop_viewport(client, page)
                    open_steps -= 1
                open_steps -= 1
                _sync_open_page_tool_wall(
                    client,
                    wall_deadline=wall_deadline,
                    total_deadline=total_deadline,
                    steps_remaining=max(1, open_steps),
                )
                wait_for_state(
                    client,
                    page,
                    """(() => ({
                      ready: !!document.querySelector('[data-testid="app-layout"]'),
                    }))()""",
                    timeout_sec=_open_page_layout_wait_sec(),
                )
                client.set_tool_wall_deadline(None)
            try:
                yield client, page
            finally:
                client.close()
            return
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
                or "response timed out" in exc_message
                or "wall budget exhausted" in exc_message
                or "connection reset" in exc_message
                or "could not connect to chrome" in exc_message
                or "unexpected server response: 404" in exc_message
                or "cdp/mux endpoint not ready" in exc_message
                or "cdp endpoint not ready" in exc_message
            ):
                if _open_page_allow_mux_budget_extension():
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
                        _wait_mux_cold_attach_drain(budget_sec=45.0)
                    except RuntimeError:
                        pass
                else:
                    try:
                        ChromeMcpClient(
                            request_timeout_sec=client_timeout_sec
                        ).recover_mux_transport()
                    except RuntimeError:
                        pass
            if parallel_transport:
                raise
            if attempt >= open_page_attempts - 1 or not _retryable_open_page_error(exc):
                raise
            time.sleep(3.0 * (attempt + 1))
    raise last_exc or RuntimeError("open_mcp_page failed without exception")


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
