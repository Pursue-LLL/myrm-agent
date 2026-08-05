"""Chrome E2E: Settings Wiki duplicate review panel after dedup scan."""

from __future__ import annotations

import json
import os
import re
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
_PANEL_WAIT_SEC = 120.0
_SETTINGS_WAIT_SEC = 90.0
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Runtime.evaluate",
    "Browser Orchestrator",
    "CDP request timeout",
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

_SETTINGS_SHELL_JS = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
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


def _force_mux_heal_before_retry() -> None:
    from tests.support.e2e_runtime_guard import _heal_stale_e2e_lease

    _heal_stale_e2e_lease()
    _require_e2e_cdp_ready(budget_sec=45.0)
    try:
        from mux_attach_force_restart import force_mux_attach_restart_scoped

        force_mux_attach_restart_scoped(reason="wiki dedup chrome outer retry")
    except RuntimeError as exc:
        if "MUX_ATTACH_RESTART_BLOCKED_PARALLEL" not in str(exc):
            raise
    time.sleep(3.0)


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


def _assert_duplicate_review_panel(client, page, *, api_url: str) -> None:
    shell = wait_for_state(
        client,
        page,
        _SETTINGS_SHELL_JS,
        timeout_sec=_warm_ui_parallel_wait_sec(_SETTINGS_WAIT_SEC),
    )
    assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

    last_state: dict[str, object] = {}
    wait_budgets = (_PANEL_WAIT_SEC, 90.0)
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


def _run_duplicate_review_assertions(
    api_url: str, ui_url: str, *, warm_route: bool = True
) -> None:
    ui_path = "/settings/wiki?wikiTab=duplicateReview"

    if warm_route:
        warm_ui_route("/settings")
        warm_ui_route(ui_path, timeout_sec=_warm_ui_parallel_wait_sec(120.0))

    seed = _seed_wiki_dedup_fixture(api_url)
    _verify_open_exact_groups_via_api(api_url)
    ui_path = str(seed.get("ui_path", ui_path))
    target_url = f"{ui_url.rstrip('/')}{ui_path}"

    with open_mcp_page(target_url, timeout_ms=120_000) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)
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
@pytest.mark.timeout(600)
def test_wiki_duplicate_review_panel_shows_exact_group() -> None:
    """Seed duplicate raw files, open Wiki duplicate review tab, assert exact group UI."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_duplicate_review_assertions, api_url, ui_url)
