"""Chrome E2E: Settings Wiki Overview health report section."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Callable

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    _trigger_attach_client_warmup_once,
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_MAX_ATTEMPTS = 2
# Post-warm budgets — keep total body < parallel bootstrap hung-reap cap (~240s).
_WIKI_SHELL_WAIT_SEC = 45.0
_WIKI_STATS_POLL_SEC = 15.0
_WIKI_STATS_LOAD_ATTEMPTS = 3
_WIKI_HEALTH_WAIT_SEC = 45.0
_WARM_ROUTE_TIMEOUT_SEC = 20.0
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Runtime.evaluate",
    "Browser Orchestrator",
    "Operation queue timeout",
    "Page.navigate",
    "Chrome MCP",
    "connection reset",
    "Page shell did not hydrate",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
    "recover_mux",
    "chrome-error",
    "E2E_ORCHESTRATOR_LEASE_DENIED",
    "ORCHESTRATOR_LEASE_DENIED",
    "E2E_USER_CLOSED_TAB",
    "lease not found",
    "wave is not open",
    "PARENT_LEASE_NOT_ACTIVE",
    "E2E_LEASE_INVALID",
    "LEASE_NOT_ACTIVE",
    "MUX_ATTACH_RESTART_BLOCKED_PARALLEL",
    "No target with given id",
    "does not own target",
    "Session with given id not found",
    "bodyLength",
    "sock.recv",
    "_read_response",
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_WARM_PLATFORM_READINESS_JS = """(async () => {
  if (sessionStorage.getItem('e2e_warm_platform_readiness') === 'true') {
    return { ok: true, cached: true };
  }
  try {
    for (let attempt = 0; attempt < 40; attempt += 1) {
      const res = await fetch('/api/v1/health/ready', { cache: 'no-store' });
      if (res.ok) {
        const body = await res.json();
        if (body?.checks?.database === true) {
          sessionStorage.setItem('e2e_warm_platform_readiness', 'true');
          return { ok: true, attempts: attempt + 1 };
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    return { ok: false, reason: 'database-not-ready' };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_WIKI_E2E_BRIDGE_READY_JS = """(() => ({
  ready:
    location.pathname.endsWith('/settings/wiki') &&
    typeof window.__MYRM_E2E_WIKI__?.inject === 'function',
  hasBridge: typeof window.__MYRM_E2E_WIKI__?.inject === 'function',
  hasShell: !!document.querySelector('[data-testid="wiki-settings-shell"]'),
}))()"""

_WIKI_E2E_HANDLERS_READY_JS = """(() => ({
  ready:
    location.pathname.endsWith('/settings/wiki') &&
    !!document.querySelector('[data-testid="wiki-settings-shell"]') &&
    typeof window.__MYRM_E2E_WIKI__?.isHandlersReady === 'function' &&
    window.__MYRM_E2E_WIKI__.isHandlersReady() === true,
  hasShell: !!document.querySelector('[data-testid="wiki-settings-shell"]'),
  handlersReady:
    typeof window.__MYRM_E2E_WIKI__?.isHandlersReady === 'function' &&
    window.__MYRM_E2E_WIKI__.isHandlersReady() === true,
}))()"""

_INJECT_WIKI_STATS_JS = """(async () => {
  const ensureOverview = () => {
    const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
    if (!shell) return false;
    const overviewTab = Array.from(shell.querySelectorAll('[role="tab"]')).find((el) =>
      /overview|概览|总览/i.test((el.textContent || '').trim()),
    );
    if (overviewTab && overviewTab.getAttribute('data-state') !== 'active') {
      overviewTab.click();
    }
    return overviewTab?.getAttribute('data-state') === 'active';
  };

  const waitHandlers = async (budgetMs) => {
    const deadline = Date.now() + budgetMs;
    while (Date.now() < deadline) {
      ensureOverview();
      if (typeof window.__MYRM_E2E_WIKI__?.isHandlersReady === 'function' &&
          window.__MYRM_E2E_WIKI__.isHandlersReady()) {
        return true;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    return false;
  };

  try {
    ensureOverview();
    const handlersReady = await waitHandlers(20000);
    const statsRes = await fetch('/api/v1/wiki/stats', { cache: 'no-store' });
    if (!statsRes.ok) {
      return { ok: false, status: statsRes.status, stage: 'stats', handlersReady };
    }
    const statsPayload = await statsRes.json();
    const statsDetail = statsPayload?.data ?? statsPayload;

    let healthDetail = null;
    const healthRes = await fetch('/api/v1/wiki/health-report', { cache: 'no-store' });
    if (healthRes.ok) {
      const healthPayload = await healthRes.json();
      healthDetail = healthPayload?.data ?? healthPayload;
    }

    const bridgeReady = typeof window.__MYRM_E2E_WIKI__?.inject === 'function';
    if (bridgeReady) {
      window.__MYRM_E2E_WIKI__.inject({ stats: statsDetail, health: healthDetail ?? undefined });
    } else {
      window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-stats', { detail: statsDetail }));
      if (healthDetail) {
        window.dispatchEvent(new CustomEvent('myrm-e2e-wiki-health-report', { detail: healthDetail }));
      }
    }

    const panelDeadline = Date.now() + 20000;
    while (Date.now() < panelDeadline) {
      ensureOverview();
      const hasPanel = !!document.querySelector('[data-testid="wiki-stats-panel"]');
      const hasHealth = !!document.querySelector('[data-testid="wiki-health-section"]');
      if (hasPanel && hasHealth) {
        return { ok: true, bridgeReady, handlersReady, hasPanel: true, hasHealth: true };
      }
      if (bridgeReady) {
        window.__MYRM_E2E_WIKI__.inject({ stats: statsDetail, health: healthDetail ?? undefined });
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    return {
      ok: true,
      bridgeReady,
      handlersReady,
      hasPanel: !!document.querySelector('[data-testid="wiki-stats-panel"]'),
      hasHealth: !!document.querySelector('[data-testid="wiki-health-section"]'),
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_CLEAR_E2E_AUTH_JS = """(() => {
  try {
    localStorage.removeItem('auth_token');
    return { ok: true };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_BROWSER_WIKI_STATS_FETCH_JS = """(async () => {
  try {
    const token = localStorage.getItem('auth_token');
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const res = await fetch('/api/v1/wiki/stats', { cache: 'no-store', headers });
    const text = await res.text();
    let parsed = null;
    try {
      parsed = JSON.parse(text);
    } catch (_err) {
      parsed = null;
    }
    return {
      ok: res.ok,
      status: res.status,
      hasToken: !!token,
      hasData: !!(parsed && (parsed.data || parsed.total_concepts != null)),
      preview: text.slice(0, 180),
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_ENSURE_WIKI_OVERVIEW_JS = """(() => {
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  if (!shell) {
    return { ok: false, reason: 'no-shell' };
  }
  const overviewTab = Array.from(shell.querySelectorAll('[role="tab"]')).find((el) =>
    /overview|概览|总览/i.test((el.textContent || '').trim()),
  );
  if (overviewTab && overviewTab.getAttribute('data-state') !== 'active') {
    overviewTab.click();
    return { ok: true, switched: true };
  }
  return { ok: true, switched: false, overviewActive: overviewTab?.getAttribute('data-state') === 'active' };
})()"""

_CLICK_LOAD_STATS_JS = """(() => {
  const panel = document.querySelector('[data-testid="wiki-stats-panel"]');
  if (panel) {
    return { clicked: false, alreadyLoaded: true };
  }
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  const overviewTab = shell
    ? Array.from(shell.querySelectorAll('[role="tab"]')).find((el) =>
        /overview|概览|总览/i.test((el.textContent || '').trim()),
      )
    : null;
  if (overviewTab && overviewTab.getAttribute('data-state') !== 'active') {
    overviewTab.click();
  }
  const loadBtn =
    document.querySelector('[data-testid="wiki-load-stats-btn"]') ||
    Array.from(document.querySelectorAll('button')).find((btn) =>
      /Load Statistics|加载统计|読み込み統計/i.test((btn.textContent || '').trim()),
    );
  if (loadBtn) {
    loadBtn.scrollIntoView({ block: 'center', inline: 'nearest' });
    loadBtn.focus();
    loadBtn.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    loadBtn.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    loadBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    return { clicked: true };
  }
  return { clicked: false, hasPanel: !!panel, overviewActive: overviewTab?.getAttribute('data-state') === 'active' };
})()"""

_WIKI_STATS_HYDRATE_JS = """(() => {
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  const panel = document.querySelector('[data-testid="wiki-stats-panel"]');
  const healthSection = document.querySelector('[data-testid="wiki-health-section"]');
  const loadBtn =
    document.querySelector('[data-testid="wiki-load-stats-btn"]') ||
    Array.from(document.querySelectorAll('button')).find((btn) =>
      /Load Statistics|加载统计|読み込み統計/i.test((btn.textContent || '').trim()),
    );
  const loading =
    document.querySelector('[data-testid="wiki-stats-loading"]') ||
    (shell && /Loading|加载中|読み込み中/i.test(shell.innerText || '') && !panel);
  return {
    ready: !!(panel || healthSection || loadBtn || loading),
    hasShell: !!shell,
    hasLoadBtn: !!loadBtn,
    hasPanel: !!panel,
    hasHealthSection: !!healthSection,
    isLoading: !!loading,
  };
})()"""

_WIKI_STATS_PANEL_JS = """(() => {
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  const panel = document.querySelector('[data-testid="wiki-stats-panel"]');
  const healthSection = document.querySelector('[data-testid="wiki-health-section"]');
  const loading =
    document.querySelector('[data-testid="wiki-stats-loading"]') ||
    (shell && !panel && /Loading|加载中|読み込み中/i.test(shell.innerText || ''));
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      (!!panel || !!healthSection || !!loading),
    hasPanel: !!panel,
    hasHealthSection: !!healthSection,
    isLoading: !!loading,
  };
})()"""

_WIKI_STATS_LOADED_JS = """(() => {
  const panel = document.querySelector('[data-testid="wiki-stats-panel"]');
  const healthSection = document.querySelector('[data-testid="wiki-health-section"]');
  const loading = document.querySelector('[data-testid="wiki-stats-loading"]');
  const loadBtn = document.querySelector('[data-testid="wiki-load-stats-btn"]');
  const shell = document.querySelector('[data-testid="wiki-settings-shell"]');
  const overviewTab = shell
    ? Array.from(shell.querySelectorAll('[role="tab"]')).find((el) =>
        /overview|概览|总览/i.test((el.textContent || '').trim()),
      )
    : null;
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      (!!panel || !!healthSection || !!loading),
    hasPanel: !!panel,
    hasHealthSection: !!healthSection,
    isLoading: !!loading,
    hasLoadBtn: !!loadBtn,
    overviewActive: overviewTab?.getAttribute('data-state') === 'active',
  };
})()"""

_WIKI_STATS_PROBE_JS = """(() => ({
  hasShell: !!document.querySelector('[data-testid="wiki-settings-shell"]'),
  hasBtn: !!document.querySelector('[data-testid="wiki-load-stats-btn"]'),
  hasPanel: !!document.querySelector('[data-testid="wiki-stats-panel"]'),
  hasHealth: !!document.querySelector('[data-testid="wiki-health-section"]'),
  isLoading: !!document.querySelector('[data-testid="wiki-stats-loading"]'),
  bodyPreview: (document.body?.innerText || '').slice(0, 320),
}))()"""

_WIKI_HEALTH_SECTION_JS = """(() => {
  const section = document.querySelector('[data-testid="wiki-health-section"]');
  const text = section?.innerText || '';
  const state = section?.getAttribute('data-state') ?? null;
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      !!section &&
      (state === 'clear' ||
        state === 'issues' ||
        state === 'loading' ||
        state === 'error'),
    state,
    textPreview: text.slice(0, 160),
  };
})()"""

_WIKI_HEALTH_PROVENANCE_ISSUES_JS = """(() => {
  const section = document.querySelector('[data-testid="wiki-health-section"]');
  const bodyText = document.body?.innerText || '';
  const sectionText = section?.innerText || '';
  const hasProvenanceCopy = /missing provenance|缺少溯源/i.test(bodyText);
  const sectionReady =
    section?.getAttribute('data-state') === 'issues' &&
    /Missing provenance|缺少溯源/i.test(sectionText);
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      hasProvenanceCopy &&
      (sectionReady || section?.getAttribute('data-state') === 'loading'),
    state: section?.getAttribute('data-state') ?? null,
    hasProvenanceCopy,
    sectionReady,
    textPreview: (sectionText || bodyText).slice(0, 240),
  };
})()"""


def _force_mux_heal_before_retry() -> None:
    from tests.support.e2e_runtime_guard import _heal_stale_e2e_lease

    _heal_stale_e2e_lease()
    _require_e2e_cdp_ready(budget_sec=20.0)
    try:
        from mux_attach_force_restart import force_mux_attach_restart_scoped

        force_mux_attach_restart_scoped(reason="wiki health chrome outer retry")
    except RuntimeError as exc:
        if "MUX_ATTACH_RESTART_BLOCKED_PARALLEL" not in str(exc):
            raise
    except (OSError, subprocess.TimeoutExpired):
        pass


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text:
        try:
            from transport_supervisor import parallel_active_test_count

            return parallel_active_test_count() > 0
        except (ImportError, OSError, RuntimeError, ValueError):
            return False
    if "React E2E bridge did not become ready" in text:
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _warm_wiki_settings_route() -> str:
    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/wiki",
        timeout_sec=_warm_ui_parallel_wait_sec(_WARM_ROUTE_TIMEOUT_SEC),
    )
    wiki_page_url = f"{get_e2e_ui_url().rstrip('/')}/settings/wiki"
    try:
        from warm_shell_registry import seal_platform_shell

        seal_platform_shell(ui_url=wiki_page_url, route_path="/settings/wiki")
    except ImportError:
        pass
    return wiki_page_url


def _seed_wiki_provenance_gap_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url.rstrip('/')}/api/v1/chats/test/seed-wiki-provenance-gap-fixture",
    )
    assert isinstance(seeded, dict)
    assert int(seeded.get("provenance_gaps") or 0) >= 1
    return seeded


def _poll_wiki_stats_loaded(
    client,
    page,
    wiki_page_url: str,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    """Soft poll — returns last snapshot instead of raising on timeout."""
    del wiki_page_url
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {"ready": False}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, _WIKI_STATS_LOADED_JS, timeout_sec=15.0)
        last = raw if isinstance(raw, dict) else {"ready": False, "raw": raw}
        if last.get("hasPanel") or last.get("hasHealthSection"):
            last["ready"] = True
            return last
        time.sleep(0.35)
    return last


def _warm_platform_readiness(client, page, wiki_page_url: str) -> dict[str, object]:
    platform_warm = client.evaluate(page, _WARM_PLATFORM_READINESS_JS, timeout_sec=45.0)
    if isinstance(platform_warm, dict) and platform_warm.get("ok") is True:
        return platform_warm
    reload_mcp_page(
        client,
        page,
        target_url=wiki_page_url,
        timeout_ms=90_000,
    )
    platform_warm = client.evaluate(page, _WARM_PLATFORM_READINESS_JS, timeout_sec=45.0)
    return (
        platform_warm
        if isinstance(platform_warm, dict)
        else {"ok": False, "warm": platform_warm}
    )


def _assert_health_section_ready(client, page, wiki_page_url: str) -> None:
    _trigger_attach_client_warmup_once(page_url=wiki_page_url)

    hydrate = wait_for_state(
        client,
        page,
        _WIKI_STATS_HYDRATE_JS,
        timeout_sec=_warm_ui_parallel_wait_sec(_WIKI_SHELL_WAIT_SEC),
        page_url=wiki_page_url,
    )
    assert hydrate.get("ready") is True, hydrate

    platform_warm = _warm_platform_readiness(client, page, wiki_page_url)
    assert platform_warm.get("ok") is True, platform_warm
    client.evaluate(page, _CLEAR_E2E_AUTH_JS, timeout_sec=10.0)
    reload_mcp_page(
        client,
        page,
        target_url=wiki_page_url,
        timeout_ms=90_000,
    )
    dismiss_blocking_modals(client, page, recover_url=wiki_page_url)
    _trigger_attach_client_warmup_once(page_url=wiki_page_url)
    client.evaluate(page, _ENSURE_WIKI_OVERVIEW_JS, timeout_sec=15.0)

    bridge = wait_for_state(
        client,
        page,
        _WIKI_E2E_BRIDGE_READY_JS,
        timeout_sec=_warm_ui_parallel_wait_sec(20.0),
        page_url=wiki_page_url,
    )
    assert bridge.get("ready") is True, bridge

    shell_raw = client.evaluate(page, _WIKI_E2E_HANDLERS_READY_JS, timeout_sec=15.0)
    shell = shell_raw if isinstance(shell_raw, dict) else {}

    injected = client.evaluate(page, _INJECT_WIKI_STATS_JS, timeout_sec=90.0)
    assert isinstance(injected, dict) and injected.get("ok") is True, injected
    if not injected.get("hasPanel"):
        click = client.evaluate(page, _CLICK_LOAD_STATS_JS, timeout_sec=15.0)
        loaded = _poll_wiki_stats_loaded(
            client,
            page,
            wiki_page_url,
            timeout_sec=_warm_ui_parallel_wait_sec(30.0),
        )
        assert loaded.get("hasPanel") is True, {
            "injected": injected,
            "click": click,
            "loaded": loaded,
            "shell": shell,
        }

    health_state = wait_for_state(
        client,
        page,
        _WIKI_HEALTH_SECTION_JS,
        timeout_sec=_warm_ui_parallel_wait_sec(_WIKI_HEALTH_WAIT_SEC),
        page_url=wiki_page_url,
    )
    assert health_state.get("ready") is True, health_state


def _run_health_report_assertions(
    api_url: str,
    ui_url: str,
) -> None:
    health = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/health-report")
    assert isinstance(health, dict)
    assert health.get("mode") == "structural"
    assert isinstance(health.get("issues"), list)
    assert isinstance(health.get("open_actions_count"), int)

    _seed_wiki_provenance_gap_fixture(api_url)
    health_after_seed = http_json(
        "GET", f"{api_url.rstrip('/')}/api/v1/wiki/health-report"
    )
    assert isinstance(health_after_seed, dict)
    issues = health_after_seed.get("issues") or []
    assert any(item.get("issue_type") == "provenance_gap" for item in issues)

    wiki_stats = http_json("GET", f"{api_url.rstrip('/')}/api/v1/wiki/stats")
    assert isinstance(wiki_stats, dict)

    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki"
    with open_wiki_settings_mcp_page(
        wiki_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)
        _assert_health_section_ready(client, page, wiki_page_url)
        state = wait_for_state(
            client,
            page,
            _WIKI_HEALTH_PROVENANCE_ISSUES_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(_WIKI_HEALTH_WAIT_SEC),
            page_url=wiki_page_url,
        )
        assert state.get("ready") is True, state
        assert (
            state.get("sectionReady") is True or state.get("hasProvenanceCopy") is True
        )


def _run_with_transport_retry(
    runner: Callable[..., None],
    api_url: str,
    ui_url: str,
) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resolved_api = get_e2e_api_url()
            runner(resolved_api, ui_url)
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_wiki_health_report_overview_and_provenance_gap() -> None:
    """API health-report + seed provenance gap + single Overview UI session."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_health_report_assertions, api_url, ui_url)
