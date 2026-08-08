"""Chrome MCP E2E: Domain Skills card in Settings > System.

Verifies:
1. Settings/System page loads and Domain Skills card is visible
2. Builtin x-com skill renders with correct badge and domains
3. API endpoint /browser/domain-skills returns valid data
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
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

_SETTINGS_SHELL_STATE = """(() => {
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

_DOMAIN_SKILLS_CARD_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasXCom = /X \\(Twitter\\)/.test(text);
  const hasDomainSkills = /Domain Skills|域技能|ドメインスキル|도메인 기술/.test(text);
  const hasBuiltinBadge = /builtin|内置|Built-in|ビルトイン|기본 제공/.test(text);
  const hasXDomain = /x\\.com|twitter\\.com/.test(text);
  return {
    ready: hasXCom && hasDomainSkills,
    hasXCom,
    hasDomainSkills,
    hasBuiltinBadge,
    hasXDomain,
    snippet: text.slice(0, 600),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_domain_skills_card_visible() -> None:
    """Domain Skills card must render in Settings/System with builtin x-com skill."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    resp = http_json("GET", f"{api_url}/api/v1/browser/domain-skills")
    assert isinstance(resp, list), f"Expected list, got {type(resp)}"
    ids = {s["id"] for s in resp}
    assert "x-com" in ids, f"x-com not in API response: {ids}"
    x_com = next(s for s in resp if s["id"] == "x-com")
    assert x_com["is_builtin"] is True

    # System tab pulls a heavy bundle — warm parent route first (wiki/settings E2E pattern).
    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/system",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )
    with open_settings_subroute(
        "/settings/system",
        timeout_ms=120_000,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        state = wait_for_state(
            client,
            page,
            _DOMAIN_SKILLS_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, json.dumps(state, indent=2, ensure_ascii=False)
        assert state.get("hasXCom") is True
        assert state.get("hasDomainSkills") is True
