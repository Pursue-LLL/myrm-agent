"""Real Chrome MCP E2E: workspace deliverable inline link → ArtifactPortal preview."""

from __future__ import annotations

import json

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

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
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
  const finalState = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {};
  return { ok: false, state: finalState };
})()"""

_DELIVERABLE_LINK_READY_JS = """(() => {
  const label = %s;
  const buttons = Array.from(document.querySelectorAll('button'));
  const hit = buttons.find((button) => (button.textContent || '').trim() === label);
  const deliverableButtons = Array.from(document.querySelectorAll('[data-testid="deliverable-reference-link"]'));
  return {
    ready: !!hit,
    count: buttons.length,
    deliverableCount: deliverableButtons.length,
    deliverableTexts: deliverableButtons.map((b) => (b.textContent || '').trim()).slice(0, 10),
    buttonTexts: buttons.map((b) => (b.textContent || '').trim()).slice(0, 15),
  };
})()"""

_CLICK_DELIVERABLE_JS = """(() => {
  const label = %s;
  const buttons = Array.from(document.querySelectorAll('button'));
  const hit = buttons.find((button) => (button.textContent || '').trim() === label);
  if (!hit) {
    return { ok: false, err: 'button-not-found' };
  }
  hit.click();
  return { ok: true };
})()"""

_PORTAL_OPEN_JS = """(() => {
  const portal = window.__myrmArtifactPortalStore?.getState?.();
  if (!portal) {
    return { ready: false, reason: 'no-portal-store' };
  }
  const tabs = portal.openTabs ?? [];
  const active =
    portal.activeTabIndex >= 0 && portal.activeTabIndex < tabs.length
      ? tabs[portal.activeTabIndex]
      : null;
  const content = active?.content ?? '';
  return {
    ready: tabs.length > 0 && typeof content === 'string' && content.includes('Deliverable E2E'),
    tabCount: tabs.length,
    filename: active?.artifact?.filename ?? null,
    contentLen: content.length,
  };
})()"""


def _seed_deliverable_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-deliverable-link-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    deliverable_path = str(seeded.get("deliverable_path") or "")
    assert chat_id.startswith("e2edeliv")
    assert deliverable_path.startswith("workspace/")
    return seeded


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_deliverable_workspace_link_opens_portal() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_deliverable_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    deliverable_path = str(seeded["deliverable_path"])

    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        attached = client.evaluate(
            page,
            _ATTACH_CHAT_JS % json.dumps(chat_id),
            timeout_sec=90.0,
        )
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        link_state = wait_for_state(
            client,
            page,
            _DELIVERABLE_LINK_READY_JS % json.dumps(deliverable_path),
            timeout_sec=60.0,
        )
        assert link_state.get("ready") is True, link_state

        clicked = client.evaluate(
            page,
            _CLICK_DELIVERABLE_JS % json.dumps(deliverable_path),
            timeout_sec=15.0,
        )
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        portal_state = wait_for_state(
            client,
            page,
            _PORTAL_OPEN_JS,
            timeout_sec=60.0,
        )
        assert portal_state.get("ready") is True, portal_state
