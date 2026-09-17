"""Real Chrome MCP E2E: Channel routing topic row renders the team identity section."""

from __future__ import annotations

import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_IDENTITY_ROW_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  const onChannels = location.pathname.includes('/settings/channels');
  if (!onChannels) {
    return { ready: false, reason: 'not-on-channels' };
  }
  const navButtons = Array.from(document.querySelectorAll('button'));
  const routingTab = navButtons.find((el) =>
    /Channel Routing|渠道路由/i.test(el.textContent || '')
  );
  if (routingTab) {
    routingTab.click();
  }
  const channelBtns = Array.from(document.querySelectorAll('button'));
  const webhookBtn = channelBtns.find((el) =>
    /^webhook$/i.test((el.textContent || '').trim())
  );
  if (webhookBtn) {
    webhookBtn.click();
  }
  const labelFound =
    /Team Identity|团队身份|チームアイデンティティ|팀 아이덴티티|Team-Identität/i.test(bodyText);
  const inputs = Array.from(document.querySelectorAll('input[placeholder]'));
  const nameInput = inputs.find((el) =>
    /Name this teammate|为伙伴取名|名前を付ける|為夥伴取名|이름 지정|Partner benennen/i.test(
      el.getAttribute('placeholder') || ''
    )
  );
  const scopeBtns = navButtons.filter((el) =>
    /^(Inherit|Shared|Private|继承|共享|独立|継承|共有|상속|공유|Vererbt|Geteilt|Unabhängig)$/i.test(
      (el.textContent || '').trim()
    )
  );
  const identityBlock = labelFound
    ? (document.body.innerText.match(/Team Identity[\\s\\S]{0,400}|团队身份[\\s\\S]{0,400}/) || [])[0] || ''
    : '';
  const emojiRe = /[\\u{1F300}-\\u{1FAFF}\\u{2600}-\\u{27BF}]/u;
  return {
    ready: Boolean(labelFound && nameInput && scopeBtns.length >= 3),
    labelFound,
    hasNameInput: Boolean(nameInput),
    scopeBtnCount: scopeBtns.length,
    identityBlockHasEmoji: emojiRe.test(identityBlock),
    bodySnippet: bodyText.slice(0, 400),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_channel_routing_topic_row_renders_team_identity() -> None:
    """Seed a named identity via API, then verify the row renders it in WebUI."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    suffix = uuid.uuid4().hex[:8]
    agent_payload = {
        "name": f"E2E Identity Agent {suffix}",
        "description": "Agent for team identity chrome e2e",
        "model": "gpt-4o",
        "systemPrompt": "You are a team Ariel.",
        "skills": [],
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", body=agent_payload)
    assert isinstance(created, dict), created
    agent_id = created["data"]["id"]

    channel_name = "webhook"
    topic_id = f"e2e_identity_chat_{suffix}"
    bound = http_json(
        "POST",
        f"{api_url}/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        body={"agentId": agent_id, "identityName": "E2E Ariel", "identityScope": "shared"},
    )
    assert isinstance(bound, dict), bound
    assert bound.get("identityName") == "E2E Ariel"

    warm_ui_route("/settings/channels?sub=routing")
    with open_settings_subroute("/settings/channels?sub=routing", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _IDENTITY_ROW_STATE,
            timeout_sec=120.0,
        )
        assert state.get("ready") is True, state
        assert state.get("identityBlockHasEmoji") is False, state
