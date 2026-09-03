"""Real Chrome MCP E2E: TaskDeliverableBundle board rendering, category filter tabs & export selection."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
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

_EXPAND_GOAL_CARD_JS = """(() => {
  const header = document.querySelector('[data-testid="goal-status-header"]');
  if (header) {
    header.click();
    return { ok: true, clicked: 'header' };
  }
  return { ok: false, err: 'header-not-found' };
})()"""

_BUNDLE_BOARD_READY_JS = """(() => {
  const board = document.querySelector('[data-testid="task-deliverable-bundle-board"]');
  const countEl = document.querySelector('[data-testid="bundle-items-count"]');
  const tabs = document.querySelector('[data-testid="bundle-category-tabs"]');
  const grid = document.querySelector('[data-testid="bundle-items-grid"]');
  const downloadAllBtn = document.querySelector('[data-testid="bundle-download-all-btn"]');

  return {
    ready: !!board,
    hasCount: !!countEl,
    itemCountText: countEl ? (countEl.textContent || '').trim() : '',
    hasTabs: !!tabs,
    hasGrid: !!grid,
    hasDownloadAllBtn: !!downloadAllBtn,
  };
})()"""

_SELECT_FIRST_ITEM_JS = """(() => {
  const checkbox = document.querySelector('[data-testid="bundle-item-checkbox-deliv-1"]');
  if (!checkbox) {
    return { ok: false, err: 'checkbox-not-found' };
  }
  checkbox.click();
  const exportBtn = document.querySelector('[data-testid="bundle-export-selected-btn"]');
  return {
    ok: true,
    checked: checkbox.checked,
    hasExportBtn: !!exportBtn,
    exportText: exportBtn ? (exportBtn.textContent || '').trim() : '',
  };
})()"""

_SWITCH_CATEGORY_TAB_JS = """(() => {
  const strategyTab = document.querySelector('[data-testid="bundle-category-tab-strategy"]');
  if (!strategyTab) {
    return { ok: false, err: 'strategy-tab-not-found' };
  }
  strategyTab.click();
  const items = Array.from(document.querySelectorAll('[data-testid^="bundle-item-deliv-"]'));
  return {
    ok: true,
    filteredItemCount: items.length,
  };
})()"""


def _seed_deliverable_bundle_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-deliverable-bundle-goal-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    deliverables = seeded.get("deliverables")
    assert chat_id.startswith("e2ebundle")
    assert isinstance(deliverables, list) and len(deliverables) >= 2
    return seeded


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_deliverable_bundle_board_renders_and_filters() -> None:
    """Seed completed Goal with deliverables → navigate to chat → expand goal card → verify board, tabs and selection."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_deliverable_bundle_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    warm_ui_route("/", timeout_sec=45.0)
    chat_url = f"{ui_url}/{chat_id}"

    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)

        # 1. Expand the GoalStatusCard header if present to reveal GoalStatusExpanded
        client.evaluate(page, _EXPAND_GOAL_CARD_JS, timeout_sec=10.0)

        # 2. Wait for the TaskDeliverableBundle board to render in DOM
        board_state = wait_for_state(
            client,
            page,
            _BUNDLE_BOARD_READY_JS,
            timeout_sec=60.0,
            page_url=chat_url,
        )
        assert board_state.get("ready") is True, f"Deliverable board not ready: {board_state}"
        assert board_state.get("hasDownloadAllBtn") is True, board_state
        assert board_state.get("itemCountText") == "3", board_state

        # 3. Test multi-selection interaction: select first item and verify dynamic export button
        select_state = client.evaluate(page, _SELECT_FIRST_ITEM_JS, timeout_sec=15.0)
        assert isinstance(select_state, dict) and select_state.get("ok") is True, select_state
        assert select_state.get("hasExportBtn") is True, select_state

        # 4. Test category filter tabs switching
        tab_switch_state = client.evaluate(page, _SWITCH_CATEGORY_TAB_JS, timeout_sec=15.0)
        assert isinstance(tab_switch_state, dict) and tab_switch_state.get("ok") is True, tab_switch_state
