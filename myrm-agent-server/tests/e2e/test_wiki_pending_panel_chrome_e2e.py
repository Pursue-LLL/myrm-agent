"""Real Chrome E2E: wiki pending panel pagination, load-more, and drift self-heal.

The pending-review panel fetches 50 drafts per page. Beyond page 1 it compares
the response stats against a closure-stable mirror of the previously seen
stats; any counter movement (a concurrent approve/reject/stage) restarts the
list from page 1 so shifted offsets can never skip or duplicate drafts. This
drives that flow against the shared stack with marker-tagged fixture drafts
(real writer path) plus a real REST approval action — no mock on the critical
path:

  seed 105 drafts -> panel first batch (50) -> load-more to 100 ->
  external REST reject of the oldest seed draft (page-3, not rendered) ->
  load-more click must drift-detect and restart at page 1 (50 items,
  stats badge synced) -> cleanup restores the pre-seed state.

Incremental API assertions anchor every UI reading, so a wrong badge or list
count is diagnosed against the authoritative stats instead of surfacing as a
UI-only diff.
"""

from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Callable

import pytest

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    wait_for_wiki_settings_shell,
    warm_ui_route,
)

_MAX_ATTEMPTS = 2
_PANEL_WAIT_SEC = 90.0
_SHELL_WAIT_SEC = 45.0
_PANEL_PATH = "/settings/wiki?wikiTab=pendingEdits"

# Reads the pending list size, the stats badge number, and the load-more
# control state. `ready` flips only when the list has settled on the expected
# item count and badge number, so an in-flight page fetch (items still at the
# previous value) never satisfies the wait early.
_PANEL_STATE_JS = """(() => {{
  const list = document.querySelector('[data-testid="pending-edits-list"]');
  const items = list ? list.children.length : 0;
  const loadMore = !!document.querySelector('[data-testid="pending-load-more"]');
  const badge = document.querySelector('[data-testid="pending-stats-badge"]');
  const badgeNum = badge ? ((badge.textContent.match(/\\d+/) || [''])[0]) : '';
  const text = list ? list.textContent : '';
  return {{
    ready: !!list && items === {expected_items} && badgeNum === {expected_badge!r},
    items,
    loadMore,
    badgeNum,
    marker104: text.includes({marker_tail_104!r}),
    marker005: text.includes({marker_tail_005!r}),
    errors: (window.__e2eErrors || []).slice(-6),
    href: location.href,
  }};
}})()"""

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_INSTALL_ERROR_HOOKS_JS = """(() => {
  window.__e2eErrors = [];
  window.onerror = (msg, src, line, col, errObj) => {
    window.__e2eErrors.push(
      `error: ${msg} @ ${src}:${line}`
      + (errObj && errObj.stack ? ` | ${errObj.stack.split('\\n').slice(0, 3).join(' <- ')}` : ''),
    );
    return false;
  };
  window.addEventListener('unhandledrejection', (e) => {
    const r = (e && e.reason) || {};
    window.__e2eErrors.push(`rejection: ${r.stack || String(r)}`);
  });
  return true;
})()"""

_LOAD_MORE_CLICK_JS = """(() => {
  const btn = document.querySelector('[data-testid="pending-load-more"]');
  if (!btn) return false;
  btn.click();
  return true;
})()"""

_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "MUX",
    "CDP",
    "Runtime.evaluate",
    "Page.navigate",
    "connection reset",
    "Page shell did not hydrate",
    "transport dead",
    "transport unavailable",
    "recover_mux",
    "chrome-error",
    "lease not found",
    "wave is not open",
    "No target with given id",
    "Session with given id not found",
    # Transient empty-panel mount (observed once on a settled stack); a full
    # runner retry re-seeds under a fresh prefix after the finally-cleanup.
    "did not become ready",
    "E2E_ROUTE_HYDRATION_TIMEOUT",
)


def _panel_state_js(concept_prefix: str, *, expected_items: int, expected_badge: str) -> str:
    """Bind the marker tails and the settled-state expectations to the probe."""
    return _PANEL_STATE_JS.format(
        expected_items=expected_items,
        expected_badge=expected_badge,
        marker_tail_104=f"{concept_prefix}-104",
        marker_tail_005=f"{concept_prefix}-005",
    )


def _shared_api_url() -> str:
    """The API origin the shared UI actually talks to (Next.js rewrite).

    The epoch pin may point ``E2E_API_BASE`` at an isolated verify candidate
    (e.g. :18080) whose database the shared UI never reads; the wiki panel
    fetches through the dev rewrite, so fixture seed/cleanup/stats/reject
    must hit the same shared origin or the panel and the API readings split
    across two databases.
    """
    port_raw = os.getenv("MYRM_BACKEND_PORT", "8080").strip()
    return f"http://127.0.0.1:{port_raw if port_raw.isdigit() else '8080'}"


def _api_pending_stats(api_url: str) -> dict[str, int]:
    body = http_json("GET", f"{api_url}/api/v1/wiki/pending?limit=1")
    assert isinstance(body, dict)
    stats = body["stats"]
    assert isinstance(stats, dict)
    return stats


def _wait_stats(api_url: str, expected_pending: int, *, timeout_sec: float = 15.0) -> dict[str, int]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, int] = {}
    while time.monotonic() < deadline:
        last = _api_pending_stats(api_url)
        if last.get("pending") == expected_pending:
            return last
        time.sleep(1.0)
    return last


def _is_transport_retryable(exc: BaseException) -> bool:
    return any(marker in str(exc) for marker in _TRANSPORT_RETRY_MARKERS)


def _parse_probe_from_error(err: str) -> dict[str, object]:
    match = re.search(r"\{.*\}", err, flags=re.DOTALL)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0).replace("'", '"'))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _force_mux_heal_before_retry() -> None:
    from tests.support.chrome_mcp_e2e import _require_e2e_cdp_ready

    _require_e2e_cdp_ready(budget_sec=20.0)


def _seal_warm_shell(panel_url: str) -> None:
    """Re-seal the platform warm shell for the wiki settings route.

    The idle-tab hygiene prune may have closed the warm shell tab after a
    previous session; without re-sealing, the owned page mounts on a cold
    shell and its panel hydration intermittently never lands.
    """
    try:
        from e2e_core.warm_shell_registry import seal_platform_shell

        seal_platform_shell(ui_url=panel_url, route_path="/settings/wiki")
    except ImportError:
        pass


def _run_panel_flow(api_url: str, ui_url: str) -> None:
    base_stats = _api_pending_stats(api_url)
    base_pending = int(base_stats["pending"])
    base_rejected = int(base_stats["rejected"])
    panel_url = f"{ui_url.rstrip('/')}{_PANEL_PATH}"
    _seal_warm_shell(panel_url)

    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-pending-drift-fixture")
    assert isinstance(seeded, dict)
    assert seeded["count"] == 105, seeded
    concept_prefix = str(seeded["concept_prefix"])
    edit_ids = list(seeded["edit_ids"])
    assert len(edit_ids) == 105, seeded
    first_badge = str(base_pending + 105)
    healed_badge = str(base_pending + 104)
    probe_first = _panel_state_js(concept_prefix, expected_items=50, expected_badge=first_badge)
    probe_second = _panel_state_js(concept_prefix, expected_items=100, expected_badge=first_badge)
    probe_healed = _panel_state_js(concept_prefix, expected_items=50, expected_badge=healed_badge)

    try:
        with open_wiki_settings_mcp_page(
            panel_url,
            timeout_ms=120_000,
            request_timeout_sec=180.0,
        ) as (client, page):
            client.evaluate(page, _INSTALL_ERROR_HOOKS_JS, timeout_sec=15.0)
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            dismiss_blocking_modals(client, page, recover_url=panel_url)

            wiki_shell = wait_for_wiki_settings_shell(
                client,
                page,
                page_url=panel_url,
                timeout_sec=_SHELL_WAIT_SEC,
            )
            assert wiki_shell.get("ready") is True, json.dumps(wiki_shell, indent=2, ensure_ascii=False)

            # First batch: 50 items, badge at base+105, load-more mounted.
            first = wait_for_state(client, page, probe_first, timeout_sec=_PANEL_WAIT_SEC)
            assert first.get("items") == 50, json.dumps(first, indent=2, ensure_ascii=False)
            assert first.get("badgeNum") == str(base_pending + 105), (
                f"stats badge must show base+105: base={base_pending} state={first}"
            )
            assert first.get("loadMore") is True, first

            # Load-more: 100 items, control stays mounted (100 < base+105).
            clicked = client.evaluate(page, _LOAD_MORE_CLICK_JS, timeout_sec=5.0)
            assert clicked is True, "load-more button not found before second batch"
            second = wait_for_state(client, page, probe_second, timeout_sec=_PANEL_WAIT_SEC)
            assert second.get("items") == 100, json.dumps(second, indent=2, ensure_ascii=False)
            assert second.get("loadMore") is True, second
            assert second.get("marker104"), f"newest seed draft must stay visible: {second}"

            # External approval action on a real REST endpoint: reject the
            # oldest seed draft (page-3 tail, not rendered) so the stats drift
            # while the loaded pages keep their visible rows.
            rejected = http_json(
                "POST", f"{api_url}/api/v1/wiki/pending/{edit_ids[0]}/reject"
            )
            assert isinstance(rejected, dict) and rejected.get("success") is True, rejected
            drifted_stats = _wait_stats(api_url, base_pending + 104)
            assert drifted_stats["pending"] == base_pending + 104, drifted_stats
            assert drifted_stats["rejected"] == base_rejected + 1, drifted_stats

            # Load-more again (offset=100): drift must restart from page 1 —
            # 100 items collapse back to 50, badge syncs to base+104, the
            # page-2 draft disappears from view, page-1 head stays visible.
            healed_click = client.evaluate(page, _LOAD_MORE_CLICK_JS, timeout_sec=5.0)
            assert healed_click is True, "load-more button not found before drift re-sync"
            healed = wait_for_state(client, page, probe_healed, timeout_sec=_PANEL_WAIT_SEC)
            assert healed.get("items") == 50, (
                f"drift must restart the list from page 1 (50 items, not append): {healed}"
            )
            assert healed.get("badgeNum") == str(base_pending + 104), (
                f"badge must sync to base+104 after drift re-sync: {healed}"
            )
            assert healed.get("marker104"), f"page-1 head draft must remain visible: {healed}"
            assert not healed.get("marker005"), (
                f"page-2 draft must be gone after the page-1 restart: {healed}"
            )
    finally:
        cleaned = http_json("POST", f"{api_url}/api/v1/chats/test/cleanup-pending-drift-fixture")
        assert isinstance(cleaned, dict)
        assert cleaned["deleted"] == 105, cleaned

    restored = _wait_stats(api_url, base_pending)
    assert restored["pending"] == base_pending, (
        f"cleanup must restore pre-seed pending count: base={base_pending} actual={restored}"
    )
    assert restored["rejected"] == base_rejected, (
        f"cleanup must restore pre-seed rejected count: base={base_rejected} actual={restored}"
    )


def _run_with_transport_retry(runner: Callable[[str, str], None], api_url: str, ui_url: str) -> None:
    last_error: BaseException | None = None
    for _attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            runner(_shared_api_url(), ui_url)
            return
        except Exception as exc:
            last_error = exc
            if _attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_pending_panel_pagination_load_more_and_drift_self_heal() -> None:
    """Drive the pending panel page flow with fixture drafts and a real reject."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    warm_ui_route("/settings")
    warm_ui_route("/settings/wiki")
    _run_with_transport_retry(_run_panel_flow, api_url, ui_url)
