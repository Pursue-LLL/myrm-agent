"""Chrome MCP E2E: WeChat Official settings + HITL draft compliance UI."""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
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
  if (!location.pathname.includes('/settings/channels')) {
    location.href = '/settings/channels';
    return {
      ready: false,
      navigating: true,
      pathname: location.pathname,
      onChannelsPath: false,
    };
  }
  const body = document.body.innerText || '';
  const tabs = Array.from(document.querySelectorAll('[role="tab"]'));
  const channelsTab = tabs.find((tab) => /消息通道|^Channels$/i.test((tab.textContent || '').trim()));
  if (channelsTab && channelsTab.getAttribute('data-state') !== 'active') {
    channelsTab.click();
  }
  const channelBtn =
    document.querySelector('[data-testid="channel-list-item-wechat_official"]') ||
    Array.from(document.querySelectorAll('button')).find((btn) =>
      /微信公众号|WeChat Official Account|微信公眾號/i.test((btn.textContent || '').trim()),
    );
  if (channelBtn) {
    channelBtn.click();
  }
  const configCard = document.querySelector('[data-testid="wechat-official-config-card"]');
  const appId = document.querySelector('#wechat-official-app-id');
  const hasHint =
    body.includes('IP 白名单') ||
    body.includes('IP whitelist') ||
    body.includes('40164');
  const loading = !!document.querySelector('.animate-pulse');
  return {
    ready: (!!appId || !!configCard) && hasHint && !loading,
    hasAppId: !!appId,
    hasConfigCard: !!configCard,
    hasHint,
    loading,
    pathname: location.pathname,
    viewportWidth: window.innerWidth,
    channelClicked: !!channelBtn,
    onChannelsPath: location.pathname.includes('/settings/channels'),
  };
})()"""

_ARTIFACT_WECHAT_PANEL_JS = """(() => {
  const openBtn =
    document.querySelector('[data-testid="wechat-draft-open-panel"]') ||
    Array.from(document.querySelectorAll('button')).find((btn) => {
      const title = (btn.getAttribute('title') || '').trim();
      return ['推送到公众号草稿', 'Push to WeChat draft'].includes(title);
    });
  if (!openBtn) {
    return { ok: false, err: 'open-panel-not-found' };
  }
  openBtn.click();
  return { ok: true };
})()"""

_CLICK_CONFIRM_PUSH_JS = """(() => {
  const confirmBtn =
    document.querySelector('[data-testid="wechat-draft-confirm-push"]') ||
    Array.from(document.querySelectorAll('button')).find((btn) => {
      const text = (btn.textContent || '').trim();
      return ['推送到草稿箱', 'Push to draft box'].includes(text);
    });
  if (!confirmBtn) {
    return { ok: false, err: 'confirm-not-found' };
  }
  if (confirmBtn.disabled) {
    return { ok: false, err: 'confirm-disabled' };
  }
  confirmBtn.click();
  return { ok: true };
})()"""

_COMPLIANCE_BLOCK_VISIBLE_JS = """(() => {
  const panel = document.querySelector('[data-testid="wechat-draft-compliance-panel"]');
  const body = document.body.innerText || '';
  const hasBlocked =
    !!panel ||
    (body.includes('集赞') &&
      (body.includes('合规') || body.includes('Compliance') || body.includes('高危') || body.includes('high risk')));
  return {
    ready: hasBlocked,
    hasPanel: !!panel,
    snippet: body.slice(0, 500),
  };
})()"""


def _wait_for_compliance_panel(
    client: object,
    page: object,
    chat_id: str,
    *,
    timeout_sec: float = 90.0,
) -> dict[str, object]:
    """Poll compliance UI without wait_for_state blank-heal (parallel E2E navigates away)."""
    del chat_id  # keep chat attached; re-attach would reset draft panel React state
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {"ready": False}
    while time.monotonic() < deadline:
        try:
            raw = client.evaluate(page, _COMPLIANCE_BLOCK_VISIBLE_JS, timeout_sec=20.0)  # type: ignore[attr-defined]
        except (RuntimeError, TimeoutError, OSError) as exc:
            last = {"ready": False, "err": str(exc)}
            time.sleep(0.5)
            continue
        if isinstance(raw, dict):
            last = raw
            if raw.get("ready") is True:
                return raw
        time.sleep(0.5)
    raise AssertionError(f"Compliance panel not visible: {last}")


def _seed_wechat_draft_fixture(api_url: str, *, variant: str = "compliance_block") -> dict[str, object]:
    last_error: BaseException | None = None
    url = f"{api_url}/api/v1/chats/test/seed-wechat-draft-fixture?variant={variant}"
    for attempt in range(1, 4):
        try:
            seeded = http_json("POST", url)
            assert isinstance(seeded, dict)
            chat_id = str(seeded.get("chat_id") or "")
            assert chat_id.startswith("e2ewxd")
            return seeded
        except (RuntimeError, AssertionError) as exc:
            last_error = exc
            if attempt >= 3:
                break
            time.sleep(min(2.0 * attempt, 6.0))
    if last_error is not None:
        raise last_error
    raise RuntimeError("WeChat draft seed failed without error detail")


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_wechat_official_settings_shows_ip_whitelist_hint() -> None:
    api_url = get_e2e_api_url()
    channels_url = f"{get_e2e_ui_url().rstrip('/')}/settings/channels"
    prepare_e2e_ui_session(api_url)

    with open_settings_subroute("/settings/channels", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=channels_url)
        state = wait_for_state(
            client,
            page,
            _SETTINGS_WECHAT_OFFICIAL_PROBE_JS,
            timeout_sec=120.0,
            page_url=channels_url,
        )
        assert state.get("ready") is True, state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_wechat_draft_panel_shows_compliance_block_for_risky_html() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_wechat_draft_fixture(api_url, variant="compliance_block")
    chat_id = str(seeded["chat_id"])
    chat_url = f"{ui_url}/{chat_id}"

    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        attached = client.evaluate(
            page,
            _ATTACH_CHAT_JS % json.dumps(chat_id),
            timeout_sec=90.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        opened = client.evaluate(page, _ARTIFACT_WECHAT_PANEL_JS, timeout_sec=30.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        panel_ready = wait_for_state(
            client,
            page,
            """(() => {
              const btn = document.querySelector('[data-testid="wechat-draft-confirm-push"]');
              return { ready: !!btn && !btn.disabled };
            })()""",
            timeout_sec=30.0,
            page_url=chat_url,
        )
        assert panel_ready.get("ready") is True, panel_ready

        clicked = client.evaluate(page, _CLICK_CONFIRM_PUSH_JS, timeout_sec=30.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        panel_state = _wait_for_compliance_panel(client, page, chat_id, timeout_sec=90.0)
        assert panel_state.get("ready") is True, panel_state
