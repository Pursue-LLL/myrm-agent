"""Real Chrome MCP E2E for Growth Center summary stats and lazy detail."""

from __future__ import annotations

import os
import urllib.parse

import pytest

from tests.support.chrome_mcp_e2e import (
    _parallel_chrome_e2e_active,
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    wait_for_state,
)


def _e2e_run_namespace() -> str:
    """Per-run namespace so parallel chrome_e2e seeds never deny each other."""
    return os.environ.get("MYRM_E2E_RUN_ID", "").strip() or f"growth-{os.getpid()}"

_GROWTH_DASHBOARD_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  if (location.pathname.includes('/settings/skills') && location.search.includes('sub=pending')) {
    const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
    const growthTab = tabs.find((el) => /Skill Growth|技能成长/i.test(el.textContent || ''));
    if (growthTab && growthTab.getAttribute('aria-selected') !== 'true') {
      growthTab.click();
    }
  }
  const summaryGrid = document.querySelector('.grid.gap-3.md\\\\:grid-cols-2.xl\\\\:grid-cols-4')
    || document.querySelector('.grid.gap-3');
  const summaryCards = summaryGrid
    ? Array.from(summaryGrid.querySelectorAll(':scope > div'))
    : [];
  const totalCard = summaryCards.find((card) =>
    /Total Cases|全部案例/i.test(card.textContent || '')
  );
  const pendingCard = summaryCards.find((card) =>
    /Pending Review|待审核/i.test(card.textContent || '')
  );
  const totalMatch = bodyText.match(/(?:Total Cases|全部案例)[\\s\\S]{0,24}(\\d+)/i);
  const pendingMatch = bodyText.match(/(?:Pending Review|待审核)[\\s\\S]{0,24}(\\d+)/i);
  const viewChangesButton = Array.from(document.querySelectorAll('button')).find((button) =>
    /View changes|查看变更/i.test(button.textContent || '')
  );
  return {
    ready:
      (/Skill Growth|技能成长/i.test(bodyText) &&
        (!!totalCard || !!totalMatch) &&
        (!!pendingCard || !!pendingMatch)),
    totalText: totalCard?.textContent || totalMatch?.[0] || '',
    pendingText: pendingCard?.textContent || pendingMatch?.[0] || '',
    hasViewChanges: !!viewChangesButton,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_growth_center_stats_and_lazy_detail_in_real_ui() -> None:
    api_url = get_e2e_api_url()

    seed_url = (
        f"{api_url}/api/v1/skills/drafts/test/seed-mock?"
        + urllib.parse.urlencode(
            {
                "agent_id": "builtin-general",
                "namespace": _e2e_run_namespace(),
            }
        )
    )
    seeded = http_json("POST", seed_url)
    assert isinstance(seeded, dict)
    created_ids = seeded.get("created_ids")
    assert isinstance(created_ids, list) and len(created_ids) >= 2
    seeded_names = seeded.get("skill_names")
    assert isinstance(seeded_names, list) and len(seeded_names) == 2

    stats_payload = http_json("GET", f"{api_url}/api/v1/skill-growth/stats")
    assert isinstance(stats_payload, dict)
    assert stats_payload.get("success") is True
    stats = stats_payload.get("data")
    assert isinstance(stats, dict)
    assert int(stats.get("total") or 0) >= 2
    assert int(stats.get("pending_review") or 0) >= 1

    cases_payload = http_json("GET", f"{api_url}/api/v1/skill-growth/cases?limit=10")
    assert isinstance(cases_payload, dict)
    case_items = cases_payload.get("data", {}).get("items")
    assert isinstance(case_items, list) and len(case_items) >= 1
    assert "original_content" not in case_items[0]
    assert "proposed_content" not in case_items[0]

    with open_settings_subroute("/settings/skills?sub=pending") as (client, page):
        dashboard_timeout = (
            _warm_ui_parallel_wait_sec(180.0)
            if _parallel_chrome_e2e_active()
            else 90.0
        )
        skills_url = f"{get_e2e_ui_url().rstrip('/')}/settings/skills?sub=pending"
        dashboard = wait_for_state(
            client,
            page,
            _GROWTH_DASHBOARD_STATE,
            timeout_sec=dashboard_timeout,
            page_url=skills_url,
        )
        total_text = str(dashboard.get("totalText") or "")
        pending_text = str(dashboard.get("pendingText") or "")
        assert any(char.isdigit() for char in total_text)
        assert any(char.isdigit() for char in pending_text)

        filter_state = client.evaluate(
            page,
            """(() => {
              const summaryGrid = document.querySelector('.grid.gap-3.md\\\\:grid-cols-2.xl\\\\:grid-cols-4');
              const summaryCards = summaryGrid
                ? Array.from(summaryGrid.querySelectorAll(':scope > div'))
                : [];
              const pendingCardText = summaryCards[1]?.textContent || '';
              const pendingFilter = Array.from(document.querySelectorAll('button')).find((button) =>
                /^(Pending|待审核)/i.test((button.textContent || '').trim())
              );
              if (!pendingFilter) {
                return { ready: false, reason: 'pending-filter-missing' };
              }
              pendingFilter.click();
              const cards = Array.from(document.querySelectorAll('.rounded-2xl.border.bg-background.p-4'));
              const caseCards = cards.filter((card) =>
                !summaryCards.includes(card) && (card.textContent || '').trim().length > 0
              );
              return {
                ready: true,
                pendingCardText,
                pendingFilterText: pendingFilter.textContent || '',
                visibleCaseCount: caseCards.length,
              };
            })()""",
            timeout_sec=5.0,
        )
        assert filter_state.get("ready") is True
        pending_card_digits = "".join(
            ch for ch in str(filter_state.get("pendingCardText") or "") if ch.isdigit()
        )
        pending_filter_digits = "".join(
            ch
            for ch in str(filter_state.get("pendingFilterText") or "")
            if ch.isdigit()
        )
        if pending_card_digits and pending_filter_digits:
            assert pending_filter_digits == pending_card_digits

        refresh_state = client.evaluate(
            page,
            """(() => {
              const refreshButton = Array.from(document.querySelectorAll('button')).find((button) =>
                /Refresh|刷新/i.test(button.textContent || '')
              );
              if (!refreshButton) return { clicked: false };
              refreshButton.click();
              return { clicked: true };
            })()""",
            timeout_sec=5.0,
        )
        assert refresh_state.get("clicked") is True
        wait_for_state(client, page, _GROWTH_DASHBOARD_STATE, timeout_sec=30.0)

        if dashboard.get("hasViewChanges") is not True:
            return

        client.evaluate(
            page,
            """(() => {
              const button = Array.from(document.querySelectorAll('button')).find((node) =>
                /View changes|查看变更/i.test(node.textContent || '')
              );
              if (!button) return { clicked: false };
              button.click();
              return { clicked: true };
            })()""",
            timeout_sec=5.0,
        )
        detail_state = wait_for_state(
            client,
            page,
            """(() => {
              const bodyText = document.body.innerText || '';
              const loading = /Loading change details|正在加载变更详情/i.test(bodyText);
              const proposed = /Proposed|建议内容/i.test(bodyText);
              const diff = /Original|原始内容/i.test(bodyText);
              return { ready: !loading && (proposed || diff), loading, proposed, diff };
            })()""",
            timeout_sec=60.0,
        )
        assert detail_state.get("ready") is True
