"""Real Chrome MCP E2E for SkillHealthPanel in /journey.

[INPUT]
- tests.support.chrome_mcp_e2e::(open_mcp_page, wait_for_state, get_e2e_ui_url) (POS: owned Chrome page + state polling)

[OUTPUT]
- test_skill_health_panel_renders_verdicts_and_filters: the panel's rows, filters and unproven wording in a real browser
- test_skill_health_panel_shows_empty_state_when_no_skill_ran: nothing to rate shows one sentence, not a list
- test_manage_link_opens_the_installed_list_filtered_by_that_skill: the row's only action lands on the skill itself

[POS]
UI-lane check of the growth dashboard's health panel. The dashboard response is replaced in the page so
the verdict mix is deterministic whatever the machine's skills did this week; the server-side verdicts are
covered by ``tests/api/statistics/skill_growth``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
)

_NAME_PREFIX = "e2e-health-"

_SKILL_HEALTH_STUB: list[dict[str, object]] = [
    {
        "skill_name": f"{_NAME_PREFIX}star",
        "health_score": 96.0,
        "status": "STAR",
        "call_count_7d": 12,
        "call_count_total": 40,
        "observed_count_7d": 12,
        "min_observed_count": 5,
        "success_rate_7d": 1.0,
        "actionable_recommendation": "Star asset.",
    },
    {
        "skill_name": f"{_NAME_PREFIX}risk",
        "health_score": 38.0,
        "status": "AT_RISK",
        "call_count_7d": 8,
        "call_count_total": 20,
        "observed_count_7d": 8,
        "min_observed_count": 5,
        "success_rate_7d": 0.375,
        "actionable_recommendation": "At-risk asset.",
    },
    {
        "skill_name": f"{_NAME_PREFIX}new",
        "health_score": 12.0,
        "status": "UNPROVEN",
        "call_count_7d": 3,
        "call_count_total": 3,
        "observed_count_7d": 2,
        "min_observed_count": 5,
        "success_rate_7d": None,
        "actionable_recommendation": "Unproven asset.",
    },
]

# Replaces ``skill_health`` of every growth-dashboard response with whatever the test last stored.
_INSTALL_STUB_JS = r"""(() => {
  if (window.__MYRM_E2E_ORIG_FETCH__) return true;
  window.__MYRM_E2E_SKILL_HEALTH__ = [];
  const orig = window.fetch.bind(window);
  window.__MYRM_E2E_ORIG_FETCH__ = orig;
  window.fetch = async (...args) => {
    const res = await orig(...args);
    const url = String(args[0] && typeof args[0] === 'object' ? args[0].url : args[0]);
    if (!url.includes('/statistics/growth-dashboard')) return res;
    try {
      const body = await res.clone().json();
      const target = body && body.data ? body.data : body;
      target.skill_health = window.__MYRM_E2E_SKILL_HEALTH__;
      return new Response(JSON.stringify(body), {
        status: res.status,
        headers: { 'Content-Type': 'application/json' },
      });
    } catch (_) {
      return res;
    }
  };
  return true;
})()"""

# Stores the next verdict list, then re-runs the dashboard fetch by switching to another time range.
_REFETCH_WITH_JS = r"""(() => {
  window.__MYRM_E2E_SKILL_HEALTH__ = __ITEMS__;
  const label = /^(__RANGE__)$/i;
  const button = Array.from(document.querySelectorAll('button')).find((b) =>
    label.test((b.textContent || '').trim())
  );
  if (!button) return false;
  button.click();
  return true;
})()"""

_CLICK_FILTER_JS = r"""(() => {
  const label = /__LABEL__/i;
  const button = Array.from(document.querySelectorAll('button')).find((b) =>
    label.test((b.textContent || '').trim())
  );
  if (!button) return false;
  button.click();
  return true;
})()"""

_PANEL_STATE_JS = r"""(() => {
  const bodyText = document.body.innerText || '';
  const buttons = Array.from(document.querySelectorAll('button'));
  const hasButton = (re) => buttons.some((b) => re.test((b.textContent || '').trim()));
  const rows = Array.from(document.querySelectorAll('[data-testid="skill-health-row"]'))
    .filter((row) => (row.getAttribute('data-skill-name') || '').startsWith('__PREFIX__'))
    .map((row) => ({ name: row.getAttribute('data-skill-name') || '', text: row.innerText || '' }));
  return {
    rows,
    hasTitle: /Skill Health|技能健康度/i.test(bodyText),
    hasEmptyCopy: /No skills ran in the last 7 days|近 7 天没有技能运行/i.test(bodyText),
    hasFilters:
      hasButton(/^(All|全部)/i) &&
      hasButton(/Needs Attention|待治理/i) &&
      hasButton(/Healthy & Stars|健康与明星/i),
    rawStatusCodes: bodyText.match(/\b(?:STAR|HEALTHY|AT_RISK|UNPROVEN|STALE)\b/g) || [],
  };
})()"""

_OPEN_MANAGE_LINK_JS = r"""(() => {
  const row = document.querySelector('[data-testid="skill-health-row"][data-skill-name="__NAME__"]');
  const link = row && row.querySelector('a[href^="/settings/skills"]');
  if (!link) return false;
  link.click();
  return true;
})()"""

_SKILLS_PAGE_STATE_JS = r"""(() => {
  const search = Array.from(document.querySelectorAll('input')).find((input) =>
    /Search installed skills|搜索已安装技能/i.test(input.placeholder || '')
  );
  const activeTabs = Array.from(document.querySelectorAll('[role="tab"][data-state="active"]')).map((tab) =>
    (tab.textContent || '').trim()
  );
  return {
    path: location.pathname,
    installedTabActive: activeTabs.some((text) => /^(Installed|已安装)/i.test(text)),
    searchValue: search ? search.value : null,
  };
})()"""

_RANGE_LABELS = {7: "7D|7天", 90: "90D|90天"}
_FILTER_LABELS = {"attention": "Needs Attention|待治理", "healthy": "Healthy & Stars|健康与明星"}


@contextmanager
def _journey_with_stub(journey_url: str) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    with open_mcp_page(journey_url) as (client, page):
        wait_for_state(
            client,
            page,
            "(() => ({ ready: /Skill Health|技能健康度/i.test(document.body.innerText || '') }))()",
            timeout_sec=120.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert client.evaluate(page, _INSTALL_STUB_JS) is True
        yield client, page


def _show(client: ChromeMcpClient, page: McpPage, items: list[dict[str, object]], days: int) -> None:
    script = _REFETCH_WITH_JS.replace("__ITEMS__", json.dumps(items)).replace("__RANGE__", _RANGE_LABELS[days])
    assert client.evaluate(page, script) is True, f"time-range button for {days} days not found"


def _click_filter(client: ChromeMcpClient, page: McpPage, name: str) -> None:
    script = _CLICK_FILTER_JS.replace("__LABEL__", _FILTER_LABELS[name])
    assert client.evaluate(page, script) is True, f"filter {name!r} not found"


def _wait_for_rows(client: ChromeMcpClient, page: McpPage, journey_url: str, expected: set[str]) -> dict[str, object]:
    names_js = json.dumps(sorted(expected))
    state = wait_for_state(
        client,
        page,
        f"""(() => {{
          const state = {_PANEL_STATE_JS.replace("__PREFIX__", _NAME_PREFIX)};
          const names = state.rows.map((row) => row.name).sort();
          return {{ ...state, ready: JSON.stringify(names) === JSON.stringify({names_js}) }};
        }})()""",
        timeout_sec=30.0,
        page_url=journey_url,
        pin_direct_blank_heal=True,
    )
    assert state.get("ready") is True, state
    return state


def _row_text(state: dict[str, object], suffix: str) -> str:
    rows = state["rows"]
    assert isinstance(rows, list)
    matches = [row["text"] for row in rows if row["name"] == f"{_NAME_PREFIX}{suffix}"]
    assert len(matches) == 1, f"row {suffix!r} missing in {rows}"
    return str(matches[0])


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_skill_health_panel_renders_verdicts_and_filters() -> None:
    journey_url = f"{get_e2e_ui_url().rstrip('/')}/journey"
    all_rows = {f"{_NAME_PREFIX}{suffix}" for suffix in ("star", "risk", "new")}
    with _journey_with_stub(journey_url) as (client, page):
        _show(client, page, _SKILL_HEALTH_STUB, days=7)
        state = _wait_for_rows(client, page, journey_url, all_rows)
        assert state["hasFilters"] is True
        assert state["rawStatusCodes"] == [], "verdicts are shown in words, never as status codes"

        assert re.search(r"38\s*%", _row_text(state, "risk")), "a rated skill shows its success rate"
        star_text = _row_text(state, "star")
        assert re.search(r"100\s*%", star_text)

        unproven_text = _row_text(state, "new")
        assert "–" in unproven_text, "an unproven skill shows no score"
        assert "%" not in unproven_text, "an unproven skill shows no success rate"
        assert re.search(r"2\s*(of|/)\s*5", unproven_text), "the missing evidence is stated as observed/required"

        _click_filter(client, page, "attention")
        _wait_for_rows(client, page, journey_url, {f"{_NAME_PREFIX}risk"})

        _click_filter(client, page, "healthy")
        _wait_for_rows(client, page, journey_url, {f"{_NAME_PREFIX}star"})


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_skill_health_panel_shows_empty_state_when_no_skill_ran() -> None:
    journey_url = f"{get_e2e_ui_url().rstrip('/')}/journey"
    with _journey_with_stub(journey_url) as (client, page):
        _show(client, page, [], days=90)
        state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const state = {_PANEL_STATE_JS.replace("__PREFIX__", _NAME_PREFIX)};
              return {{ ...state, ready: state.hasEmptyCopy }};
            }})()""",
            timeout_sec=30.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert state.get("ready") is True, state
        assert state["hasFilters"] is False
        assert state["rows"] == []


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_manage_link_opens_the_installed_list_filtered_by_that_skill() -> None:
    journey_url = f"{get_e2e_ui_url().rstrip('/')}/journey"
    at_risk = f"{_NAME_PREFIX}risk"
    with _journey_with_stub(journey_url) as (client, page):
        _show(client, page, _SKILL_HEALTH_STUB, days=7)
        _wait_for_rows(client, page, journey_url, {f"{_NAME_PREFIX}{suffix}" for suffix in ("star", "risk", "new")})

        assert client.evaluate(page, _OPEN_MANAGE_LINK_JS.replace("__NAME__", at_risk)) is True

        state = wait_for_state(
            client,
            page,
            f"""(() => {{
              const state = {_SKILLS_PAGE_STATE_JS};
              return {{ ...state, ready: state.searchValue === {json.dumps(at_risk)} }};
            }})()""",
            timeout_sec=120.0,
            page_url=journey_url,
            pin_direct_blank_heal=True,
        )
        assert state.get("ready") is True, state
        assert state["path"] == "/settings/skills"
        assert state["installedTabActive"] is True, "the link must not land on the skill market"
