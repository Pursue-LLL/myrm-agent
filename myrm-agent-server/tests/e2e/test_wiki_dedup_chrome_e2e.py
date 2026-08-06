"""Chrome E2E: Settings Wiki duplicate review panel after dedup scan."""

from __future__ import annotations

import json
import os
import re
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
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_MAX_ATTEMPTS = 2
# Post-warm budgets — keep total body < parallel bootstrap hung-reap cap (~240s).
_PANEL_WAIT_SEC = 45.0
_WIKI_SHELL_WAIT_SEC = 45.0
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

_ACTIVATE_DEDUP_TAB_JS = """(() => {
  const tab = document.querySelector('[data-testid="wiki-dedup-tab"]');
  if (!tab) {
    return { ok: false, reason: 'missing_tab' };
  }
  if (tab.getAttribute('data-state') !== 'active') {
    tab.click();
  }
  return {
    ok: true,
    active: tab.getAttribute('data-state') === 'active',
  };
})()"""

_WIKI_SHELL_JS = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="wiki-dedup-tab"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""

_TRIGGER_DEDUP_SCAN_JS = """(() => {
  const panel = document.querySelector('[data-testid="wiki-dedup-panel"]');
  const text = panel?.innerText || '';
  if (/Group #|组 #/.test(text)) {
    return { triggered: false, reason: 'already_has_group' };
  }
  const scanBtn = document.querySelector('[data-testid="wiki-dedup-scan-btn"]');
  scanBtn?.click();
  return { triggered: Boolean(scanBtn), reason: 'clicked_scan' };
})()"""

_DEDUP_PANEL_READY_JS = """(() => {
  const panel = document.querySelector('[data-testid="wiki-dedup-panel"]');
  const scanBtn = document.querySelector('[data-testid="wiki-dedup-scan-btn"]');
  const dedupTab = document.querySelector('[data-testid="wiki-dedup-tab"]');
  const text = panel?.innerText || '';
  const hasExactBadge = /Exact duplicate|精确重复/.test(text);
  const hasGroup = /Group #|组 #/.test(text);
  return {
    ready: Boolean(panel && scanBtn && dedupTab && hasExactBadge && hasGroup),
    hasPanel: Boolean(panel),
    hasScanBtn: Boolean(scanBtn),
    hasExactBadge,
    hasGroup,
    dedupTabActive: dedupTab?.getAttribute('data-state') === 'active',
    pathname: location.pathname,
    search: location.search,
    snippet: text.slice(0, 500),
  };
})()"""


def _restart_browser_orchestrator_for_retry() -> None:
    """Soft-restart orchestrator daemon so CDP plane picks up dist/ changes."""
    import shutil
    import subprocess
    from pathlib import Path

    monorepo_root = Path(__file__).resolve().parents[4]
    daemon_bin = monorepo_root / "scripts/dev/browser-orchestrator/dist/bin/main.js"
    ensure_sh = monorepo_root / "scripts/dev/ensure-browser-orchestrator.sh"
    pid_path = (
        Path.home()
        / ".local/state/myrm-browser-orchestrator/daemon.pid"
    )
    node = shutil.which("node")
    if not node or not daemon_bin.is_file() or not ensure_sh.is_file():
        return
    if pid_path.is_file():
        raw_pid = pid_path.read_text(encoding="utf-8").strip()
        try:
            old_pid = int(raw_pid)
        except ValueError:
            old_pid = 0
        if old_pid > 0:
            subprocess.run(
                ["kill", str(old_pid)],
                timeout=5,
                check=False,
                capture_output=True,
                text=True,
            )
            time.sleep(1.0)
        pid_path.unlink(missing_ok=True)
    subprocess.run(
        [node, str(daemon_bin), "stop"],
        cwd=str(monorepo_root),
        timeout=20,
        check=False,
        capture_output=True,
        text=True,
    )
    time.sleep(1.0)
    env = {**os.environ, "MYRM_BROWSER_ORCHESTRATOR": "1"}
    subprocess.run(
        ["bash", str(ensure_sh)],
        cwd=str(monorepo_root),
        env=env,
        timeout=30,
        check=False,
        capture_output=True,
        text=True,
    )


def _force_mux_heal_before_retry() -> None:
    from tests.support.e2e_runtime_guard import _heal_stale_e2e_lease

    _heal_stale_e2e_lease()
    _require_e2e_cdp_ready(budget_sec=45.0)
    _restart_browser_orchestrator_for_retry()
    try:
        from pathlib import Path

        from e2e_warm_ui_heal import heal_shared_frontend_debounced

        monorepo_root = Path(__file__).resolve().parents[4]
        heal_shared_frontend_debounced(
            monorepo_root,
            debounce_sec=0.0,
            subprocess_timeout_sec=45.0,
        )
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    try:
        from mux_attach_force_restart import force_mux_attach_restart_scoped

        force_mux_attach_restart_scoped(reason="wiki dedup chrome outer retry")
    except RuntimeError as exc:
        if "MUX_ATTACH_RESTART_BLOCKED_PARALLEL" not in str(exc):
            raise
    except (OSError, subprocess.TimeoutExpired):
        pass
    time.sleep(2.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text:
        return False
    if "React E2E bridge did not become ready" in text:
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _seed_wiki_dedup_fixture(api_url: str) -> dict[str, object]:
    payload = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-wiki-dedup-fixture",
        expected_statuses=frozenset({200}),
    )
    assert isinstance(payload, dict)
    assert int(payload.get("open_groups", 0)) >= 1, payload
    assert int(payload.get("exact_groups", 0)) >= 1, payload
    return payload


def _verify_open_exact_groups_via_api(api_url: str) -> None:
    groups = http_json("GET", f"{api_url}/api/v1/wiki/dedup/groups")
    assert isinstance(groups, list), groups
    open_exact = [
        group
        for group in groups
        if isinstance(group, dict)
        and group.get("status") in {"open", "deferred"}
        and group.get("tier") == "exact"
    ]
    assert open_exact, groups


def _parse_probe_from_error(err: str) -> dict[str, object]:
    match = re.search(r"\{.*\}", err, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0).replace("'", '"'))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _client_navigate(client, page, url: str) -> None:
    """In-page navigation — avoids CDP Page.navigate stalls under parallel Chrome load."""
    client.evaluate(
        page,
        f"(() => {{ window.location.href = {json.dumps(url)}; return location.href; }})()",
        timeout_sec=15.0,
    )


def _ensure_client_at_path(client, page, url: str, *, expected_suffix: str) -> None:
    last_err: BaseException | None = None
    for _attempt in range(1, 4):
        try:
            _client_navigate(client, page, url)
            time.sleep(2.0)
            probe = client.evaluate(
                page,
                "(() => ({ pathname: location.pathname, bodyLength: (document.body?.innerText || '').length }))()",
                timeout_sec=15.0,
            )
            if isinstance(probe, dict) and str(probe.get("pathname", "")).endswith(
                expected_suffix
            ):
                return
        except (RuntimeError, TimeoutError, OSError) as exc:
            last_err = exc
            time.sleep(1.0)
    if last_err is not None:
        raise RuntimeError(
            f"Client navigation to {url!r} did not reach {expected_suffix!r}: {last_err}"
        ) from last_err
    raise RuntimeError(
        f"Client navigation to {url!r} did not reach {expected_suffix!r} after retries"
    )


def _navigate_to_duplicate_review(client, page, ui_url: str) -> None:
    wiki_url = f"{ui_url.rstrip('/')}/settings/wiki"

    _ensure_client_at_path(client, page, wiki_url, expected_suffix="/settings/wiki")
    wiki_shell = wait_for_state(
        client,
        page,
        _WIKI_SHELL_JS,
        timeout_sec=_WIKI_SHELL_WAIT_SEC,
        page_url=wiki_url,
    )
    assert wiki_shell.get("ready") is True, json.dumps(wiki_shell, indent=2, ensure_ascii=False)
    dismiss_blocking_modals(client, page, recover_url=wiki_url)

    tab_state = client.evaluate(page, _ACTIVATE_DEDUP_TAB_JS, timeout_sec=15.0)
    assert isinstance(tab_state, dict) and tab_state.get("ok") is True, tab_state
    time.sleep(1.0)


def _assert_duplicate_review_panel(client, page, *, api_url: str) -> None:
    last_state: dict[str, object] = {}
    wait_budgets = (_PANEL_WAIT_SEC, 30.0)
    for attempt, wait_sec in enumerate(wait_budgets):
        try:
            last_state = wait_for_state(
                client,
                page,
                _DEDUP_PANEL_READY_JS,
                timeout_sec=wait_sec,
            )
        except AssertionError as exc:
            last_state = {"ready": False, "err": str(exc)}
        if last_state.get("ready") is True:
            return
        probe = _parse_probe_from_error(str(last_state.get("err", "")))
        if attempt == 0 and probe.get("hasPanel") is True:
            _seed_wiki_dedup_fixture(api_url)
            _verify_open_exact_groups_via_api(api_url)
            client.evaluate(page, _TRIGGER_DEDUP_SCAN_JS, timeout_sec=15.0)
            time.sleep(2.0)
            continue
    raise AssertionError(json.dumps(last_state, indent=2, ensure_ascii=False))


def _should_use_about_blank_open() -> bool:
    try:
        from transport_supervisor import parallel_active_test_count

        return parallel_active_test_count() > 0
    except (ImportError, OSError, RuntimeError, ValueError):
        return True


def _run_duplicate_review_assertions(
    api_url: str,
    ui_url: str,
    *,
    warm_route: bool = True,
) -> None:
    _seed_wiki_dedup_fixture(api_url)
    _verify_open_exact_groups_via_api(api_url)
    if warm_route:
        warm_ui_route(
            "/settings/wiki",
            timeout_sec=_warm_ui_parallel_wait_sec(_WARM_ROUTE_TIMEOUT_SEC),
        )

    # about:blank — orchestrator skips CDP navigate; client-nav to pre-warmed wiki route.
    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki"
    open_url = "about:blank" if _should_use_about_blank_open() else wiki_page_url

    with open_mcp_page(
        open_url,
        timeout_ms=60_000,
        request_timeout_sec=90.0,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        if open_url == "about:blank":
            _navigate_to_duplicate_review(client, page, ui_url)
        else:
            dismiss_blocking_modals(client, page, recover_url=wiki_page_url)
            tab_state = client.evaluate(page, _ACTIVATE_DEDUP_TAB_JS, timeout_sec=15.0)
            assert isinstance(tab_state, dict) and tab_state.get("ok") is True, tab_state
            time.sleep(1.0)
        _assert_duplicate_review_panel(client, page, api_url=api_url)


def _run_with_transport_retry(
    runner: Callable[..., None],
    api_url: str,
    ui_url: str,
) -> None:
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resolved_api = get_e2e_api_url()
            runner(resolved_api, ui_url, warm_route=(attempt == 1))
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
@pytest.mark.timeout(300)
def test_wiki_duplicate_review_panel_shows_exact_group() -> None:
    """Seed duplicate raw files, open Wiki duplicate review tab, assert exact group UI."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_duplicate_review_assertions, api_url, ui_url)
