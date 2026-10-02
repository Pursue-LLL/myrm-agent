"""Real Chrome E2E: wiki pending panel pagination, load-more, and drift self-heal.

The pending-review panel fetches 50 drafts per page. Beyond page 1 it compares
the response stats against a closure-stable mirror of the previously seen
stats; any counter movement (a concurrent approve/reject/stage) restarts the
list from page 1 so shifted offsets can never skip or duplicate drafts. This
drives that flow with marker-tagged fixture drafts (real writer path) plus a
real REST approval action — no mock on the critical path:

  seed 105 drafts -> panel first batch (50) -> load-more to 100 ->
  external REST reject of the oldest seed draft (page-3, not rendered) ->
  load-more click must drift-detect and restart at page 1 (50 items,
  stats badge synced) -> cleanup restores the pre-seed state.

Incremental API assertions anchor every UI reading, so a wrong badge or list
count is diagnosed against the authoritative stats instead of surfacing as a
UI-only diff.
"""

from __future__ import annotations

import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
    open_mcp_page,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_PANEL_PATH = "/settings/wiki?wikiTab=pendingEdits"

# Reads the pending list size, the stats badge number, and the load-more
# control state. `ready` only flips once the list container has mounted.
_PANEL_STATE_JS = """(() => {{
  const list = document.querySelector('[data-testid="pending-edits-list"]');
  const items = list ? list.children.length : 0;
  const loadMore = !!document.querySelector('[data-testid="pending-load-more"]');
  const badge = [...document.querySelectorAll('span')]
    .find((s) => String(s.className).includes('bg-amber-500/10'));
  const badgeNum = badge ? ((badge.textContent.match(/\\d+/) || [''])[0]) : '';
  const text = list ? list.textContent : '';
  return {{
    ready: !!list,
    items,
    loadMore,
    badgeNum,
    marker104: text.includes({marker_tail_104!r}),
    marker005: text.includes({marker_tail_005!r}),
    href: location.href,
  }};
}})()"""


def _panel_state_js(concept_prefix: str) -> str:
    """Bind the marker tails (newest seed draft + page-2 draft) to the probe."""
    return _PANEL_STATE_JS.format(
        marker_tail_104=f"{concept_prefix}-104",
        marker_tail_005=f"{concept_prefix}-005",
    )


def _api_pending_stats(api_url: str) -> dict[str, int]:
    body = http_json("GET", f"{api_url}/api/v1/wiki/pending?limit=1")
    return body["stats"]


def _wait_stats(api_url: str, expected_pending: int, *, timeout_sec: float = 15.0) -> dict[str, int]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, int] = {}
    while time.monotonic() < deadline:
        last = _api_pending_stats(api_url)
        if last.get("pending") == expected_pending:
            return last
        time.sleep(1.0)
    return last


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
def test_pending_panel_pagination_load_more_and_drift_self_heal() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    panel_url = f"{ui_url}{_PANEL_PATH}"

    warm_ui_route("/settings/wiki")

    base_stats = _api_pending_stats(api_url)
    base_pending = int(base_stats["pending"])
    base_rejected = int(base_stats["rejected"])

    seeded: dict[str, object] = {}
    try:
        with open_mcp_page(panel_url) as (client, page):
            navigate_mcp_page(client, page, panel_url, timeout_ms=90_000)

            seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-pending-drift-fixture")
            assert seeded["count"] == 105
            concept_prefix = str(seeded["concept_prefix"])
            edit_ids = list(seeded["edit_ids"])
            assert len(edit_ids) == 105
            probe = _panel_state_js(concept_prefix)

            # First batch: 50 items, badge at base+105, load-more mounted.
            reload_mcp_page(client, page, target_url=panel_url, timeout_ms=90_000, ignore_cache=True)
            first = wait_for_state(client, page, probe, timeout_sec=90.0, page_url=_PANEL_PATH)
            assert first["items"] == 50, f"first batch must be 50 items: {first}"
            assert first["badgeNum"] == str(base_pending + 105), (
                f"stats badge must show base+105: base={base_pending} state={first}"
            )
            assert first["loadMore"] is True, first

            # Load-more: 100 items, control stays mounted (100 < base+105).
            client.evaluate(
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="pending-load-more"]');
                  if (!btn) return false;
                  btn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            second = wait_for_state(client, page, probe, timeout_sec=90.0, page_url=_PANEL_PATH)
            assert second["items"] == 100, f"load-more must reach 100 items: {second}"
            assert second["loadMore"] is True, second
            assert second["marker104"], f"newest seed draft must stay visible: {second}"

            # External approval action on a real REST endpoint: reject the
            # oldest seed draft (page-3 tail, not rendered) so the stats drift
            # while the loaded pages keep their visible rows.
            rejected = http_json(
                "POST", f"{api_url}/api/v1/wiki/pending/{edit_ids[0]}/reject"
            )
            assert rejected.get("success") is True, rejected
            drifted_stats = _wait_stats(api_url, base_pending + 104)
            assert drifted_stats["pending"] == base_pending + 104, drifted_stats
            assert drifted_stats["rejected"] == base_rejected + 1, drifted_stats

            # Load-more again (offset=100): drift must restart from page 1 —
            # 100 items collapse back to 50, badge syncs to base+104, the
            # page-2 draft disappears from view, page-1 head stays visible.
            client.evaluate(
                page,
                """(() => {
                  const btn = document.querySelector('[data-testid="pending-load-more"]');
                  if (!btn) return false;
                  btn.click();
                  return true;
                })()""",
                timeout_sec=5.0,
            )
            healed = wait_for_state(client, page, probe, timeout_sec=90.0, page_url=_PANEL_PATH)
            assert healed["items"] == 50, (
                f"drift must restart the list from page 1 (50 items, not append): {healed}"
            )
            assert healed["badgeNum"] == str(base_pending + 104), (
                f"badge must sync to base+104 after drift re-sync: {healed}"
            )
            assert healed["marker104"], f"page-1 head draft must remain visible: {healed}"
            assert not healed["marker005"], (
                f"page-2 draft must be gone after the page-1 restart: {healed}"
            )
    finally:
        cleaned = http_json("POST", f"{api_url}/api/v1/chats/test/cleanup-pending-drift-fixture")
        assert cleaned["deleted"] == 105, cleaned

    restored = _wait_stats(api_url, base_pending)
    assert restored["pending"] == base_pending, (
        f"cleanup must restore pre-seed pending count: base={base_pending} actual={restored}"
    )
    assert restored["rejected"] == base_rejected, (
        f"cleanup must restore pre-seed rejected count: base={base_rejected} actual={restored}"
    )
