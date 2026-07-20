"""Real Chrome MCP E2E for external_cli builtin gate (local toggle + setup hints)."""

from __future__ import annotations

import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
)

_AGENT_EDITOR_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[data-testid="app-layout"]') &&
    !!document.querySelector('[data-testid="agent-tab-capabilities"]'),
  url: location.href,
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

_BUILTIN_DIALOG_READY_JS = """(() => ({
  ready:
    !!document.querySelector('[role="dialog"]') &&
    !!document.querySelector('[data-testid="builtin-external_cli"]'),
}))()"""

_EXTERNAL_CLI_LOCAL_ASSERT_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-external_cli"]');
  if (!card) {
    return { ok: false, reason: 'missing-card' };
  }
  const disabled = card.getAttribute('aria-disabled') === 'true' || card.hasAttribute('disabled');
  const text = document.body?.innerText || '';
  const hasLocalOnlyHint = /local or desktop mode|本地或桌面模式/i.test(text);
  return {
    ok: !disabled && !hasLocalOnlyHint,
    disabled,
    hasLocalOnlyHint,
  };
})()"""

_TOGGLE_EXTERNAL_CLI_JS = """(() => {
  const card = document.querySelector('[data-testid="builtin-external_cli"]');
  if (!card) {
    return { toggled: false, reason: 'missing-card' };
  }
  card.click();
  return { toggled: true };
})()"""

_EXTERNAL_CLI_SETUP_HINT_JS = """(() => {
  const text = document.body?.innerText || '';
  return {
    ready:
      (/Settings.*Developer.*External Agents|设置.*开发者.*外部/i.test(text) ||
        /Configure External Agents|配置外部/i.test(text)) &&
      (/external CLI|外部 CLI|CLI backend|CLI 后端/i.test(text)),
  };
})()"""


def _create_editable_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"External CLI E2E {suffix}",
        "description": "Chrome E2E for external_cli builtin gate",
        "system_prompt": "You are a test agent.",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search"],
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_external_cli_builtin_card_enabled_in_local_chrome_ui() -> None:
    """Local deploy: external_cli card is togglable and shows setup hints when enabled."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    agent_id = _create_editable_agent(api_url)
    agent_settings_url = f"{ui_url}/settings/agents?agentId={agent_id}"

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
            assert opened.get("clicked") is True, f"Built-in Tools card not found: {opened}"

            wait_for_state(client, page, _BUILTIN_DIALOG_READY_JS, timeout_sec=30.0)

            local_state = client.evaluate(page, _EXTERNAL_CLI_LOCAL_ASSERT_JS, timeout_sec=10.0)
            assert isinstance(local_state, dict)
            assert local_state.get("ok") is True, f"external_cli should be enabled in local UI: {local_state}"

            toggled = client.evaluate(page, _TOGGLE_EXTERNAL_CLI_JS, timeout_sec=10.0)
            assert isinstance(toggled, dict)
            assert toggled.get("toggled") is True, f"Failed to toggle external_cli: {toggled}"

            hint = wait_for_state(client, page, _EXTERNAL_CLI_SETUP_HINT_JS, timeout_sec=30.0)
            assert hint.get("ready") is True, f"Missing externalCli setup hint: {hint}"
    finally:
        _delete_agent(api_url, agent_id)
