"""Real Chrome MCP E2E for planning builtin tool and task progress rendering."""

from __future__ import annotations

import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_agent_settings_editor,
    wait_for_state,
)

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

_PLANNING_DIALOG_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[role="dialog"]') &&
    !!document.querySelector('[data-testid="builtin-planning"]'),
}))()"""

_PLANNING_CARD_ASSERT_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-planning"]');
  if (!card) {
    return { ok: false, reason: 'missing-card' };
  }
  const disabled =
    card.getAttribute('aria-disabled') === 'true' || card.hasAttribute('disabled');
  const text = document.body?.innerText || '';
  const hasPlanningLabel = /Multi-Step Progress|多步进度/i.test(text);
  return {
    ok: !disabled && hasPlanningLabel,
    disabled,
    hasPlanningLabel,
  };
})()"""

_TOGGLE_PLANNING_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-planning"]');
  if (!card) {
    return { toggled: false, reason: 'missing-card' };
  }
  card.click();
  return { toggled: true };
})()"""

_PLANNING_ENABLED_ASSERT_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-planning"]');
  if (!card) {
    return { ready: false, reason: 'missing-card' };
  }
  const checkedRing = card.querySelector('.bg-primary.border-primary');
  const checkedBorder = /border-primary\\/30/.test(card.className);
  return {
    ready: !!checkedRing || checkedBorder,
    hasCheckedRing: !!checkedRing,
    checkedBorder,
  };
})()"""


def _create_editable_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Planning E2E {suffix}",
        "description": "Chrome E2E for planning builtin gate",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "memory"],
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = created.get("data", {}).get("id") if isinstance(created.get("data"), dict) else created.get("id")
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


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_planning_builtin_card_visible_and_togglable_in_chrome_ui() -> None:
    """Planning opt-in card is visible in Built-in Tools dialog and can be enabled."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    agent_id = _create_editable_agent(api_url)
    agent_subroute = f"/settings/agents?agentId={agent_id}#loadout"

    try:
        with open_settings_subroute(
            agent_subroute,
            layout_timeout_sec=90.0,
        ) as (client, page):
            editor_ready = wait_for_agent_settings_editor(
                client,
                page,
                page_url=f"{ui_url.rstrip('/')}{agent_subroute}",
                timeout_sec=90.0,
            )
            assert editor_ready.get("ready") is True, editor_ready
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
            assert opened.get("clicked") is True, f"Built-in Tools card not found: {opened}"

            wait_for_state(client, page, _PLANNING_DIALOG_READY_JS, timeout_sec=30.0)

            card_state = client.evaluate(page, _PLANNING_CARD_ASSERT_JS, timeout_sec=10.0)
            assert isinstance(card_state, dict)
            assert card_state.get("ok") is True, f"planning card should be visible and enabled: {card_state}"

            toggled = client.evaluate(page, _TOGGLE_PLANNING_JS, timeout_sec=10.0)
            assert isinstance(toggled, dict)
            assert toggled.get("toggled") is True, f"Failed to toggle planning: {toggled}"

            enabled = wait_for_state(client, page, _PLANNING_ENABLED_ASSERT_JS, timeout_sec=15.0)
            assert enabled.get("ready") is True, f"planning should be enabled after toggle: {enabled}"
    finally:
        _delete_agent(api_url, agent_id)

