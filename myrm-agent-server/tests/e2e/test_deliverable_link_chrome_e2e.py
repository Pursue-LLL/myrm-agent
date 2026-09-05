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
    wait_for_react_e2e_bridge,
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

_SCROLL_MESSAGES_JS = """(() => {
  const scrollEl = document.querySelector('.overflow-y-auto');
  if (scrollEl) {
    scrollEl.scrollTop = scrollEl.scrollHeight;
  }
  window.scrollTo(0, document.body.scrollHeight);
  return { ok: true };
})()"""

_DELIVERABLE_LINK_READY_JS = """(() => {
  const label = %s;
  const deliverableButtons = Array.from(
    document.querySelectorAll('[data-testid="deliverable-reference-link"]'),
  );
  const hit = deliverableButtons.find(
    (button) => (button.textContent || '').trim() === label,
  );
  const domMessageCount = document.querySelectorAll('[data-message-id]').length;
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistant = msgs.find((m) => m?.role === 'assistant');
  return {
    ready: !!hit,
    deliverableCount: deliverableButtons.length,
    domMessageCount,
    storeMessageCount: msgs.length,
    loading: Boolean(store?.loading),
    assistantHasPath: Boolean(
      assistant?.content && String(assistant.content).includes(label),
    ),
  };
})()"""

_CLICK_DELIVERABLE_JS = """(() => {
  const label = %s;
  const deliverableButtons = Array.from(
    document.querySelectorAll('[data-testid="deliverable-reference-link"]'),
  );
  const hit = deliverableButtons.find(
    (button) => (button.textContent || '').trim() === label,
  );
  if (!hit) {
    return { ok: false, err: 'deliverable-link-not-found' };
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
    """Seed fixture → navigate to chat → click workspace deliverable link → portal preview."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_deliverable_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    deliverable_path = str(seeded["deliverable_path"])

    warm_ui_route("/", timeout_sec=45.0)
    chat_url = f"{ui_url}/{chat_id}"
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        client.evaluate(page, _SCROLL_MESSAGES_JS, timeout_sec=10.0)

        link_state = wait_for_state(
            client,
            page,
            _DELIVERABLE_LINK_READY_JS % json.dumps(deliverable_path),
            timeout_sec=120.0,
            page_url=chat_url,
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

        # Verify Deliverable Confidence Tier Badge is rendered
        badge_state = client.evaluate(
            page,
            """(() => {
                const badge = document.querySelector('[data-testid="deliverable-tier-badge-artifact"]');
                return {
                    found: !!badge,
                    text: badge ? (badge.textContent || '').trim() : '',
                };
            })()""",
            timeout_sec=10.0,
        )
        assert isinstance(badge_state, dict)
        # In seeded chat history, the badge should render if deliverableTier is present on the message
        assert badge_state.get("found") is True, badge_state

        # Verify Staged Artifacts Notice Banner is rendered and interactive
        notice_state = client.evaluate(
            page,
            """(() => {
                const notice = document.querySelector('[data-testid="staged-artifacts-notice"]');
                return {
                    found: !!notice,
                    text: notice ? (notice.textContent || '').trim() : '',
                };
            })()""",
            timeout_sec=10.0,
        )
        assert isinstance(notice_state, dict)
        assert notice_state.get("found") is True, notice_state
        assert "draft_worker.py" in str(notice_state.get("text", ""))

        # Verify Staged Artifacts Notice Banner is rendered and interactive
        notice_state = client.evaluate(
            page,
            """(() => {
                const notice = document.querySelector('[data-testid="staged-artifacts-notice"]');
                return {
                    found: !!notice,
                    text: notice ? (notice.textContent || '').trim() : '',
                };
            })()""",
            timeout_sec=10.0,
        )
        assert isinstance(notice_state, dict)
        assert notice_state.get("found") is True, notice_state
        assert ".myrm/staged_artifacts/" in str(notice_state.get("text", ""))
