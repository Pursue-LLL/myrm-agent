"""Chrome MCP E2E: WeChat Official settings + HITL draft compliance UI."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    localStorage.setItem('myrm-selected-channel', 'wechat_official');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_ATTACH_CHAT_JS = """(async () => {
  const chatId = %s;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {
    return { ok: false, err: 'no-bridge' };
  }
  await bridge.attachToChat(chatId);
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {};
    if (
      state.chatId === chatId
      && state.isMessagesLoaded === true
      && state.notFound !== true
      && state.loadError !== true
      && (state.messageCount ?? 0) >= 1
    ) {
      return { ok: true, state };
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return { ok: false, state: window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {} };
})()"""

_SETTINGS_WECHAT_OFFICIAL_PROBE_JS = """(() => {
  try {
    window.resizeTo(1280, 900);
  } catch {
    // ignore
  }
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
    localStorage.setItem('myrm-selected-channel', 'wechat_official');
  } catch {
    // ignore
  }
  const labels = ['微信公众号', 'WeChat Official Account'];
  const buttons = Array.from(document.querySelectorAll('button'));
  const channelBtn = buttons.find((btn) =>
    labels.some((label) => (btn.textContent || '').includes(label)),
  );
  if (channelBtn) {
    channelBtn.click();
  }
  const appId = document.querySelector('#wechat-official-app-id');
  const body = document.body.innerText || '';
  const hasHint =
    body.includes('IP 白名单') ||
    body.includes('IP whitelist') ||
    body.includes('40164');
  const loading = !!document.querySelector('.animate-spin');
  return {
    ready: !!appId && hasHint && !loading,
    hasAppId: !!appId,
    hasHint,
    loading,
    pathname: location.pathname,
    viewportWidth: window.innerWidth,
    channelClicked: !!channelBtn,
  };
})()"""

_ARTIFACT_WECHAT_PANEL_JS = """(() => {
  const labels = ['推送到公众号草稿', 'Push to WeChat draft'];
  const buttons = Array.from(document.querySelectorAll('button'));
  const openBtn = buttons.find((btn) => {
    const title = (btn.getAttribute('title') || '').trim();
    return labels.some((label) => title === label);
  });
  if (!openBtn) {
    return { ok: false, err: 'open-panel-not-found', titles: buttons.map((b) => b.getAttribute('title')).filter(Boolean).slice(0, 20) };
  }
  openBtn.click();
  return { ok: true };
})()"""

_COMPLIANCE_BLOCK_VISIBLE_JS = """(() => {
  const body = document.body.innerText || '';
  const hasBlocked =
    body.includes('集赞') &&
    (body.includes('合规') || body.includes('Compliance') || body.includes('高危') || body.includes('high risk'));
  return {
    ready: hasBlocked,
    snippet: body.slice(0, 500),
  };
})()"""

_CLICK_CONFIRM_PUSH_JS = """(() => {
  const labels = ['确认推送', 'Push to draft'];
  const buttons = Array.from(document.querySelectorAll('button'));
  const confirmBtn = buttons.find((btn) => labels.includes((btn.textContent || '').trim()));
  if (!confirmBtn) {
    return { ok: false, err: 'confirm-not-found', labels: buttons.map((b) => (b.textContent || '').trim()).slice(0, 20) };
  }
  confirmBtn.click();
  return { ok: true };
})()"""


def _prepare_wechat_official_settings(api_url: str) -> None:
    """Seed credentials and best-effort enable channel so config card renders."""
    http_json(
        "PUT",
        f"{api_url}/api/v1/config/wechatOfficialCredentials",
        {
            "deviceId": "wechat-settings-e2e",
            "value": {
                "appId": "wx_e2e_settings",
                "appSecret": "e2e_settings_secret",
                "token": "",
                "encodingAesKey": "",
            },
        },
    )
    http_json(
        "PATCH",
        f"{api_url}/api/v1/channels/manage/wechat_official/toggle",
        {"enabled": True},
        expected_statuses=frozenset({200, 409}),
    )


def _seed_wechat_draft_fixture(api_url: str, *, variant: str = "compliance_block") -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-wechat-draft-fixture?variant={variant}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2ewxd")
    return seeded


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_wechat_official_settings_shows_ip_whitelist_hint() -> None:
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    _prepare_wechat_official_settings(api_url)

    with open_settings_subroute("/settings/channels") as (client, page):
        state = wait_for_state(
            client,
            page,
            _SETTINGS_WECHAT_OFFICIAL_PROBE_JS,
            timeout_sec=90.0,
        )
        assert state.get("ready") is True, state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_wechat_draft_panel_shows_compliance_block_for_risky_html() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_wechat_draft_fixture(api_url, variant="compliance_block")
    chat_id = str(seeded["chat_id"])

    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        attached = client.evaluate(
            page,
            _ATTACH_CHAT_JS % json.dumps(chat_id),
            timeout_sec=90.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        opened = client.evaluate(page, _ARTIFACT_WECHAT_PANEL_JS, timeout_sec=30.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        clicked = client.evaluate(page, _CLICK_CONFIRM_PUSH_JS, timeout_sec=30.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        panel_state = wait_for_state(
            client,
            page,
            _COMPLIANCE_BLOCK_VISIBLE_JS,
            timeout_sec=60.0,
        )
        assert panel_state.get("ready") is True, panel_state
