"""Chrome E2E: Team Assets Hub renders built-in badge and localized agent names.

Verifies the built-in agent localization contract end to end:
1. `GET /api/v1/user-agents` returns `is_built_in: true` for built-in agents (data contract).
2. Settings > Memory > Team Hub renders the built-in badge (`loadout.teamHub.builtIn`).
3. Built-in agent names are localized via `getBuiltinAgentName` (no raw English name leak in zh UI).
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_TEAM_HUB_SUBROUTE = "/settings/memory?sub=team-hub"

_FOLLOW_UPS_SUBROUTE = "/settings/memory?sub=follow-ups"

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_FOLLOW_UPS_STATE_JS = """(() => {
  const lang = (document.documentElement.lang || '').toLowerCase();
  const bodyText = document.body.innerText || '';
  const isZh = lang.startsWith('zh');
  const onFollowUps =
    location.pathname.startsWith('/settings/memory') &&
    (location.search.includes('sub=follow-ups') || location.search.includes('sub=followUps'));
  const agentFilter = Array.from(document.querySelectorAll('select option')).map((o) => o.textContent.trim());
  const hasLocalizedAgentName = isZh
    ? agentFilter.includes('通用助手') || agentFilter.includes('General Assistant')
    : agentFilter.includes('General Assistant');
  const leaksEnglishName = isZh && agentFilter.includes('General Assistant');
  const filterLabel = isZh ? /智能体/.test(bodyText) : /Agent/i.test(bodyText);
  return {
    ready: onFollowUps && hasLocalizedAgentName,
    onFollowUps,
    hasLocalizedAgentName,
    leaksEnglishName,
    agentFilter,
    filterLabel,
    lang,
    pathname: location.pathname,
    search: location.search,
    snippet: bodyText.slice(0, 500),
  };
})()"""

_TEAM_HUB_STATE_JS = """(() => {
  const lang = (document.documentElement.lang || '').toLowerCase();
  const bodyText = document.body.innerText || '';
  const isZh = lang.startsWith('zh');
  const onTeamHub =
    location.pathname.startsWith('/settings/memory') &&
    (location.search.includes('sub=team-hub') || location.search.includes('sub=teamHub'));
  const hasTitle = isZh ? /团队资产/.test(bodyText) : /Team Assets/i.test(bodyText);
  const hasBuiltinBadge = isZh ? /内置/.test(bodyText) : /Built-in/i.test(bodyText);
  const hasLocalizedName = isZh ? /通用助手/.test(bodyText) : /General Assistant/i.test(bodyText);
  const leaksEnglishName = isZh && /General Assistant/.test(bodyText);
  const agentRows = document.querySelectorAll('a[href*="/settings/agents?agentId=builtin-"]').length;
  return {
    ready: onTeamHub && hasTitle && hasBuiltinBadge && hasLocalizedName && agentRows > 0,
    onTeamHub,
    hasTitle,
    hasBuiltinBadge,
    hasLocalizedName,
    leaksEnglishName,
    agentRows,
    lang,
    pathname: location.pathname,
    search: location.search,
    snippet: bodyText.slice(0, 500),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_team_hub_renders_builtin_badge_and_localized_names() -> None:
    """Team Hub must render built-in badge and localized built-in agent names."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # Data contract: built-in agents are flagged is_built_in by the backend.
    resp = http_json("GET", f"{api_url}/api/v1/user-agents?page=1&page_size=100")
    items = resp["data"]["items"]
    assert isinstance(items, list)
    general = next((item for item in items if item.get("id") == "builtin-general"), None)
    assert general is not None, "builtin-general missing from user-agents API"
    assert general.get("is_built_in") is True
    builtin_ids = {item.get("id") for item in items if item.get("is_built_in")}
    assert "builtin-general" in builtin_ids

    # Memory tab pulls a heavy bundle — warm parent route first (settings E2E pattern).
    warm_ui_route("/settings")
    with open_settings_subroute(
        _TEAM_HUB_SUBROUTE,
        timeout_ms=120_000,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        state = wait_for_state(
            client,
            page,
            _TEAM_HUB_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("hasTitle") is True
        assert state.get("hasBuiltinBadge") is True
        assert state.get("hasLocalizedName") is True
        assert state.get("agentRows") and state["agentRows"] > 0
        assert state.get("leaksEnglishName") is False, "zh UI leaked raw English built-in agent name; getBuiltinAgentName missing"

        # Follow-ups tab: built-in agent name in the agent filter dropdown must be localized.
        client.navigate(
            page,
            f"{get_e2e_ui_url().rstrip('/')}{_FOLLOW_UPS_SUBROUTE}",
            timeout_ms=90_000,
        )
        follow_state = wait_for_state(
            client,
            page,
            _FOLLOW_UPS_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(60.0),
        )
        assert follow_state.get("ready") is True, json.dumps(follow_state, indent=2, ensure_ascii=False)
        assert follow_state.get("hasLocalizedAgentName") is True
        assert follow_state.get("leaksEnglishName") is False, (
            "zh UI leaked raw English built-in agent name in follow-ups filter; getBuiltinAgentName missing"
        )
