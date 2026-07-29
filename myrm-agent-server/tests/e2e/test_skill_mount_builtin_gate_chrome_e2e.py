"""READ lane Chrome E2E: skill_market / skill_manage builtin toggles (v1-min mount SSOT)."""

from __future__ import annotations

import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_AGENT_EDITOR_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-testid="app-layout"]') &&
    !!document.querySelector('[data-testid="agent-tab-capabilities"]'),
}))()"""

_CLICK_CAPABILITIES_JS = """(() => {
  const capTab = document.querySelector('[data-testid="agent-tab-capabilities"]');
  if (capTab && capTab.getAttribute('aria-selected') !== 'true') {
    capTab.click();
  }
  return { clicked: true };
})()"""

_OPEN_BUILTIN_DIALOG_JS = """(() => {
  const builtinCard = Array.from(document.querySelectorAll('button')).find((btn) =>
    /Built-in Tools|内置工具/i.test(btn.textContent || ''),
  );
  if (!builtinCard) {
    return { clicked: false };
  }
  builtinCard.click();
  return { clicked: true };
})()"""

_SKILL_MOUNT_DIALOG_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[role="dialog"]') &&
    !!document.querySelector('[data-testid="builtin-skill_market"]') &&
    !!document.querySelector('[data-testid="builtin-skill_manage"]'),
}))()"""

_SKILL_MARKET_DEFAULT_OFF_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-skill_market"]');
  if (!card) {
    return { ok: false, reason: 'missing-skill_market' };
  }
  const checkedRing = card.querySelector('.bg-primary.border-primary');
  const checkedBorder = /border-primary\\/30/.test(card.className);
  const enabled = !!checkedRing || checkedBorder;
  const text = document.body?.innerText || '';
  const hasLabel = /Skill Market|技能市场/i.test(text);
  return { ok: !enabled && hasLabel, enabled, hasLabel };
})()"""

_TOGGLE_SKILL_MARKET_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-skill_market"]');
  if (!card) {
    return { toggled: false, reason: 'missing-skill_market' };
  }
  card.click();
  return { toggled: true };
})()"""

_SKILL_MARKET_ENABLED_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-skill_market"]');
  if (!card) {
    return { ready: false, reason: 'missing-skill_market' };
  }
  const checkedRing = card.querySelector('.bg-primary.border-primary');
  const checkedBorder = /border-primary\\/30/.test(card.className);
  return {
    ready: !!checkedRing || checkedBorder,
    hasCheckedRing: !!checkedRing,
    checkedBorder,
  };
})()"""


def _create_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Skill Mount E2E {suffix}",
        "description": "Chrome READ E2E for skill_market/skill_manage toggles",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "memory", "structured_clarify"],
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = (
        created.get("data", {}).get("id")
        if isinstance(created.get("data"), dict)
        else created.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _delete_agent(api_url: str, agent_id: str) -> None:
    try:
        http_json(
            "DELETE",
            f"{api_url}/api/v1/user-agents/{agent_id}",
            expected_statuses=frozenset({200, 204}),
        )
    except RuntimeError:
        pass


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
def test_skill_market_and_manage_builtin_cards_default_off_and_togglable() -> None:
    """skill_market / skill_manage cards visible; default OFF; skill_market toggles ON."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    agent_id = _create_agent(api_url)
    agent_settings_url = f"{ui_url}/settings/agents?agentId={agent_id}"
    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/settings/agents?agentId={agent_id}")

    try:
        with open_mcp_page(agent_settings_url) as (client, page):
            wait_for_state(client, page, _AGENT_EDITOR_READY_JS, timeout_sec=90.0)
            client.evaluate(page, _CLICK_CAPABILITIES_JS, timeout_sec=10.0)
            wait_for_state(
                client,
                page,
                """(() => ({
                  ready: /Built-in Tools|内置工具/i.test(document.body?.innerText || ''),
                }))()""",
                timeout_sec=30.0,
            )
            opened = client.evaluate(page, _OPEN_BUILTIN_DIALOG_JS, timeout_sec=15.0)
            assert isinstance(opened, dict)
            assert (
                opened.get("clicked") is True
            ), f"Built-in Tools card not found: {opened}"

            wait_for_state(client, page, _SKILL_MOUNT_DIALOG_READY_JS, timeout_sec=30.0)

            default_off = client.evaluate(
                page, _SKILL_MARKET_DEFAULT_OFF_JS, timeout_sec=10.0
            )
            assert isinstance(default_off, dict)
            assert (
                default_off.get("ok") is True
            ), f"skill_market should default OFF for v1-min: {default_off}"

            toggled = client.evaluate(page, _TOGGLE_SKILL_MARKET_JS, timeout_sec=10.0)
            assert isinstance(toggled, dict)
            assert (
                toggled.get("toggled") is True
            ), f"Failed to toggle skill_market: {toggled}"

            enabled = wait_for_state(
                client, page, _SKILL_MARKET_ENABLED_JS, timeout_sec=15.0
            )
            assert (
                enabled.get("ready") is True
            ), f"skill_market should be enabled after toggle: {enabled}"
    finally:
        _delete_agent(api_url, agent_id)
