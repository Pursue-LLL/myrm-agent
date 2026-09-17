"""Real Chrome MCP E2E: Channel routing topic row renders the team identity section."""

from __future__ import annotations

import time
import uuid

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    reload_mcp_page,
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


_FOLLOWUP_TOGGLE_JS = """(() => {
  const navButtons0 = Array.from(document.querySelectorAll('button'));
  const routingTab0 = navButtons0.find((el) =>
    /Channel Routing|渠道路由/i.test(el.textContent || '')
  );
  if (routingTab0) {
    routingTab0.click();
  }
  const channelBtns0 = Array.from(document.querySelectorAll('button'));
  const webhookBtn0 = channelBtns0.find((el) =>
    /^webhook$/i.test((el.textContent || '').trim())
  );
  if (webhookBtn0) {
    webhookBtn0.click();
  }
  const TOPIC = '__TOPIC__';
  const cands = Array.from(document.querySelectorAll('div')).filter((d) => (d.innerText || '').includes(TOPIC));
  cands.sort((a, b) => (a.innerText.length - b.innerText.length));
  let scope = null;
  for (const d of cands) {
    const t = d.innerText || '';
    if (/(Receipts|完工回执)/.test(t) && /(Stall nudge|停滞提醒)/.test(t)) { scope = d; break; }
  }
  if (!scope) {
    return { ready: false, ok: false, reason: 'row-missing' };
  }
  const btns = Array.from(scope.querySelectorAll('button'));
  const byText = (re) => btns.find((el) => re.test((el.textContent || '').trim()));
  const receipts = byText(/^(Receipts|完工回执|完了レシート|完工回執|완료 레시트|Belege)$/);
  const stall = byText(/^(Stall nudge|停滞提醒|停滞nudge|停滯提醒|정체 nudge|Stau-Nudge)$/);
  if (!receipts || !stall) {
    return { ready: false, reason: 'followup-buttons-missing' };
  }
  return { ready: true };
})()"""

_FOLLOWUP_CLICK_JS = """(() => {
  const navButtons0 = Array.from(document.querySelectorAll('button'));
  const routingTab0 = navButtons0.find((el) =>
    /Channel Routing|渠道路由/i.test(el.textContent || '')
  );
  if (routingTab0) {
    routingTab0.click();
  }
  const channelBtns0 = Array.from(document.querySelectorAll('button'));
  const webhookBtn0 = channelBtns0.find((el) =>
    /^webhook$/i.test((el.textContent || '').trim())
  );
  if (webhookBtn0) {
    webhookBtn0.click();
  }
  const TOPIC = '__TOPIC__';
  const cands = Array.from(document.querySelectorAll('div')).filter((d) => (d.innerText || '').includes(TOPIC));
  cands.sort((a, b) => (a.innerText.length - b.innerText.length));
  let scope = null;
  for (const d of cands) {
    const t = d.innerText || '';
    if (/(Receipts|完工回执)/.test(t) && /(Stall nudge|停滞提醒)/.test(t)) { scope = d; break; }
  }
  if (!scope) {
    return { ready: false, ok: false, reason: 'row-missing' };
  }
  const btns = Array.from(scope.querySelectorAll('button'));
  const byText = (re) => btns.find((el) => re.test((el.textContent || '').trim()));
  const receipts = byText(/^(Receipts|完工回执|完了レシート|完工回執|완료 레시트|Belege)$/);
  const stall = byText(/^(Stall nudge|停滞提醒|停滞nudge|停滯提醒|정체 nudge|Stau-Nudge)$/);
  if (!receipts || !stall) {
    return { ok: false, reason: 'followup-buttons-missing' };
  }
  const wasReceiptsOn = (receipts.className || '').includes('bg-primary');
  const wasStallOn = (stall.className || '').includes('bg-primary');
  if (receipts.disabled) {
    return { ok: false, reason: 'saving-in-flight', wasReceiptsOn, wasStallOn };
  }
  receipts.click();
  return { ok: true, wasReceiptsOn, wasStallOn, clicked: 'receipts' };
})()"""

_FOLLOWUP_CLICK_STALL_JS = """(() => {
  const TOPIC = '__TOPIC__';
  const cands = Array.from(document.querySelectorAll('div')).filter((d) => (d.innerText || '').includes(TOPIC));
  cands.sort((a, b) => (a.innerText.length - b.innerText.length));
  let scope = null;
  for (const d of cands) {
    const t = d.innerText || '';
    if (/(Receipts|完工回执)/.test(t) && /(Stall nudge|停滞提醒)/.test(t)) { scope = d; break; }
  }
  if (!scope) {
    return { ready: false, ok: false, reason: 'row-missing' };
  }
  const btns = Array.from(scope.querySelectorAll('button'));
  const byText = (re) => btns.find((el) => re.test((el.textContent || '').trim()));
  const stall = byText(/^(Stall nudge|停滞提醒|停滞nudge|停滯提醒|정체 nudge|Stau-Nudge)$/);
  if (!stall) {
    return { ok: false, reason: 'stall-button-missing' };
  }
  if (stall.disabled) {
    return { ok: false, reason: 'saving-in-flight' };
  }
  stall.click();
  return { ok: true, clicked: 'stall' };
})()"""

_FOLLOWUP_RECEIPTS_OFF_JS = """(() => {
  const TOPIC = '__TOPIC__';
  const cands = Array.from(document.querySelectorAll('div')).filter((d) => (d.innerText || '').includes(TOPIC));
  cands.sort((a, b) => (a.innerText.length - b.innerText.length));
  let scope = null;
  for (const d of cands) {
    const t = d.innerText || '';
    if (/(Receipts|完工回执)/.test(t) && /(Stall nudge|停滞提醒)/.test(t)) { scope = d; break; }
  }
  if (!scope) {
    return { ready: false, ok: false, reason: 'row-missing' };
  }
  const btns = Array.from(scope.querySelectorAll('button'));
  const byText = (re) => btns.find((el) => re.test((el.textContent || '').trim()));
  const receipts = byText(/^(Receipts|完工回执|完了レシート|完工回執|완료 레시트|Belege)$/);
  const stall = byText(/^(Stall nudge|停滞提醒|停滞nudge|停滯提醒|정체 nudge|Stau-Nudge)$/);
  if (!receipts || !stall) {
    return { ready: false, reason: 'followup-buttons-missing' };
  }
  const receiptsOn = (receipts.className || '').includes('bg-primary');
  const stallOn = (stall.className || '').includes('bg-primary');
  const disabled = Boolean(receipts.disabled || stall.disabled);
  return { ready: receiptsOn === false && disabled === false, receiptsOn, stallOn, disabled };
})()"""

_FOLLOWUP_READ_JS = """(() => {
  const navButtons0 = Array.from(document.querySelectorAll('button'));
  const routingTab0 = navButtons0.find((el) =>
    /Channel Routing|渠道路由/i.test(el.textContent || '')
  );
  if (routingTab0) {
    routingTab0.click();
  }
  const channelBtns0 = Array.from(document.querySelectorAll('button'));
  const webhookBtn0 = channelBtns0.find((el) =>
    /^webhook$/i.test((el.textContent || '').trim())
  );
  if (webhookBtn0) {
    webhookBtn0.click();
  }
  const TOPIC = '__TOPIC__';
  const cands = Array.from(document.querySelectorAll('div')).filter((d) => (d.innerText || '').includes(TOPIC));
  cands.sort((a, b) => (a.innerText.length - b.innerText.length));
  let scope = null;
  for (const d of cands) {
    const t = d.innerText || '';
    if (/(Receipts|完工回执)/.test(t) && /(Stall nudge|停滞提醒)/.test(t)) { scope = d; break; }
  }
  if (!scope) {
    return { ready: false, ok: false, reason: 'row-missing' };
  }
  const btns = Array.from(scope.querySelectorAll('button'));
  const byText = (re) => btns.find((el) => re.test((el.textContent || '').trim()));
  const receipts = byText(/^(Receipts|完工回执|完了レシート|完工回執|완료 레시트|Belege)$/);
  const stall = byText(/^(Stall nudge|停滞提醒|停滞nudge|停滯提醒|정체 nudge|Stau-Nudge)$/);
  if (!receipts || !stall) {
    return { ready: false, reason: 'followup-buttons-missing' };
  }
  const receiptsOn = (receipts.className || '').includes('bg-primary');
  const stallOn = (stall.className || '').includes('bg-primary');
  return { ready: true, receiptsOn, stallOn };
})()"""

_FOLLOWUP_FLIPPED_JS = """(() => {
  const navButtons0 = Array.from(document.querySelectorAll('button'));
  const routingTab0 = navButtons0.find((el) =>
    /Channel Routing|渠道路由/i.test(el.textContent || '')
  );
  if (routingTab0) {
    routingTab0.click();
  }
  const channelBtns0 = Array.from(document.querySelectorAll('button'));
  const webhookBtn0 = channelBtns0.find((el) =>
    /^webhook$/i.test((el.textContent || '').trim())
  );
  if (webhookBtn0) {
    webhookBtn0.click();
  }
  const TOPIC = '__TOPIC__';
  const cands = Array.from(document.querySelectorAll('div')).filter((d) => (d.innerText || '').includes(TOPIC));
  cands.sort((a, b) => (a.innerText.length - b.innerText.length));
  let scope = null;
  for (const d of cands) {
    const t = d.innerText || '';
    if (/(Receipts|完工回执)/.test(t) && /(Stall nudge|停滞提醒)/.test(t)) { scope = d; break; }
  }
  if (!scope) {
    return { ready: false, ok: false, reason: 'row-missing' };
  }
  const btns = Array.from(scope.querySelectorAll('button'));
  const byText = (re) => btns.find((el) => re.test((el.textContent || '').trim()));
  const receipts = byText(/^(Receipts|完工回执|完了レシート|完工回執|완료 레시트|Belege)$/);
  const stall = byText(/^(Stall nudge|停滞提醒|停滞nudge|停滯提醒|정체 nudge|Stau-Nudge)$/);
  if (!receipts || !stall) {
    return { ready: false, reason: 'followup-buttons-missing' };
  }
  const receiptsOn = (receipts.className || '').includes('bg-primary');
  const stallOn = (stall.className || '').includes('bg-primary');
  const flipped = receiptsOn === false && stallOn === true;
  return { ready: flipped, receiptsOn, stallOn };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_channel_routing_followup_switches_persist_across_reload() -> None:
    """A real user toggles follow-up switches; reload proves server persistence."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    suffix = uuid.uuid4().hex[:8]
    agent_payload = {
        "name": f"E2E FollowUp Agent {suffix}",
        "description": "Agent for follow-up switch chrome e2e",
        "model": "gpt-4o",
        "systemPrompt": "You are a team Ariel.",
        "skills": [],
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", body=agent_payload)
    assert isinstance(created, dict), created
    agent_id = created["data"]["id"]

    channel_name = "webhook"
    topic_id = f"e2e_followup_chat_{suffix}"
    bound = http_json(
        "POST",
        f"{api_url}/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        body={"agentId": agent_id},
    )
    assert isinstance(bound, dict), bound

    warm_ui_route("/settings/channels?sub=routing")
    with open_settings_subroute("/settings/channels?sub=routing", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        present = wait_for_state(client, page, _FOLLOWUP_TOGGLE_JS.replace("__TOPIC__", topic_id), timeout_sec=120.0)
        assert present.get("ready") is True, present
        clicked = client.evaluate(page, _FOLLOWUP_CLICK_JS.replace("__TOPIC__", topic_id), timeout_sec=30.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked
        assert clicked.get("wasReceiptsOn") is True, clicked
        assert clicked.get("wasStallOn") is False, clicked
        settled = wait_for_state(client, page, _FOLLOWUP_RECEIPTS_OFF_JS.replace("__TOPIC__", topic_id), timeout_sec=60.0)
        assert settled.get("ready") is True, settled
        clicked_stall: dict[str, object] | None = None
        for _ in range(12):
            attempt = client.evaluate(page, _FOLLOWUP_CLICK_STALL_JS.replace("__TOPIC__", topic_id), timeout_sec=30.0)
            assert isinstance(attempt, dict), attempt
            if attempt.get("ok") is True:
                clicked_stall = attempt
                break
            time.sleep(5.0)
        assert clicked_stall is not None and clicked_stall.get("ok") is True, clicked_stall
        flipped = wait_for_state(client, page, _FOLLOWUP_FLIPPED_JS.replace("__TOPIC__", topic_id), timeout_sec=60.0)
        assert flipped.get("ready") is True, flipped
        reload_mcp_page(client, page, timeout_ms=90_000)
        dismiss_blocking_modals(client, page)
        state = wait_for_state(client, page, _FOLLOWUP_READ_JS.replace("__TOPIC__", topic_id), timeout_sec=120.0)
        assert state.get("ready") is True, state
        assert state.get("receiptsOn") is False, state
        assert state.get("stallOn") is True, state
