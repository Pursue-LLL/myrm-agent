"""Chrome E2E: artifact inline annotations end to end (Lane-B).

Seeded deliverable chat -> open ArtifactPortal -> toggle annotation panel ->
select preview text + intent -> Add -> list shows the comment and localStorage
persists it -> reload -> comment survives. Zero mocks, isolated namespace,
no residue (annotations live in the test browser profile only).
"""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
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

_OPEN_FIRST_DELIVERABLE_JS = """(() => {
  if (!document.body) return { ok: false, reason: 'no-body' };
  const scroller = document.querySelector('.overflow-y-auto');
  if (scroller) {
    scroller.scrollTop = scroller.scrollHeight;
  }
  window.scrollTo(0, document.body.scrollHeight);
  const link = document.querySelector('[data-testid="deliverable-reference-link"]');
  if (!link) {
    const count = document.querySelectorAll('[data-message-id]').length;
    return { ok: false, reason: 'no-link', messages: count };
  }
  link.click();
  return { ok: true };
})()"""

_PORTAL_STORE_READY_JS = """(() => {
  const portal = window.__myrmArtifactPortalStore?.getState?.();
  if (!portal) return { ready: false, reason: 'no-portal-store' };
  const tabs = portal.openTabs ?? [];
  return { ready: tabs.length > 0, tabCount: tabs.length };
})()"""

_PORTAL_WITH_TEXT_JS = """(() => {
  const container = document.getElementById('artifact-content-container');
  const text = container ? (container.innerText || '') : '';
  return { ready: !!container && text.includes('Deliverable E2E'), len: text.length };
})()"""

_OPEN_PANEL_JS = """(() => {
  const btn = document.querySelector('[data-testid="annotation-toggle"]');
  if (!btn) return { ok: false, reason: 'no-toggle' };
  btn.click();
  return { ok: true };
})()"""

_PANEL_READY_JS = """(() => {
  const panel = document.querySelector('section[aria-label="Artifact annotations"]');
  return { ready: !!panel };
})()"""

_ADD_COMMENT_JS = """((args) => {
  const container = document.getElementById('artifact-content-container');
  if (!container) return { ok: false, reason: 'no-container' };
  const walker = document.createTreeWalker(container, NodeFilter.SHOW_TEXT);
  let node = null;
  while (walker.nextNode()) {
    if ((walker.currentNode.textContent || '').includes('Deliverable E2E')) {
      node = walker.currentNode;
      break;
    }
  }
  if (!node) return { ok: false, reason: 'no-text' };
  const range = document.createRange();
  range.selectNodeContents(node);
  const selection = window.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  const inputs = Array.from(document.querySelectorAll('section[aria-label="Artifact annotations"] input'));
  const intent = inputs[0];
  if (!intent) return { ok: false, reason: 'no-intent' };
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
  setter.call(intent, args.intent);
  intent.dispatchEvent(new Event('input', { bubbles: true }));
  const add = Array.from(document.querySelectorAll('section[aria-label="Artifact annotations"] button'))
    .find((b) => /^(Add comment|添加批注|新增批註)$/.test((b.textContent || '').trim()));
  if (!add) return { ok: false, reason: 'no-add' };
  add.click();
  return { ok: true };
})(__ARGS__)"""

_LIST_READY_JS = """((args) => {
  const panel = document.querySelector('section[aria-label="Artifact annotations"]');
  const txt = panel ? (panel.innerText || '') : '';
  const stored = window.localStorage.getItem('myrm.artifact-annotations.v1') || '';
  return { ready: txt.includes(args.intent), stored: stored.includes(args.intent) };
})(__ARGS__)"""


def _seed_deliverable_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-deliverable-link-fixture")
    assert isinstance(seeded, dict)
    return seeded


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_artifact_annotation_panel_roundtrip_via_ui() -> None:
    """Annotation toggle -> panel -> add comment -> persisted across reload."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_deliverable_fixture(api_url)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2edeliv"), seeded

    intent = "E2E review note: verify this paragraph"
    warm_ui_route("/", timeout_sec=45.0)
    chat_url = f"{ui_url}/{chat_id}"
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        navigate_mcp_page(client, page, chat_url, timeout_ms=90_000)

        # T1: open the seeded deliverable, then the portal shows its content.
        # The message list streams in, so retry the click until it lands.
        link: dict | None = None
        deadline = time.monotonic() + 120.0
        while time.monotonic() < deadline:
            link = client.evaluate(page, _OPEN_FIRST_DELIVERABLE_JS, timeout_sec=15.0)
            if isinstance(link, dict) and link.get("ok"):
                break
            time.sleep(3.0)
        assert isinstance(link, dict) and link.get("ok") is True, link
        store_state = wait_for_state(client, page, _PORTAL_STORE_READY_JS, timeout_sec=90.0)
        assert store_state.get("ready") is True, json.dumps(store_state, ensure_ascii=False)
        content = wait_for_state(client, page, _PORTAL_WITH_TEXT_JS, timeout_sec=120.0)
        assert content.get("ready") is True, json.dumps(content, ensure_ascii=False)

        # T2: toggle opens the annotation panel.
        opened = client.evaluate(page, _OPEN_PANEL_JS, timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, json.dumps(panel, ensure_ascii=False)

        # T3: select text + intent + Add stores the comment and persists it.
        added = client.evaluate(
            page,
            _ADD_COMMENT_JS.replace(
                "__ARGS__",
                json.dumps({"intent": intent, "addLabel": "Add comment"}),
            ),
            timeout_sec=20.0,
        )
        assert isinstance(added, dict) and added.get("ok") is True, added
        listed = wait_for_state(
            client,
            page,
            _LIST_READY_JS.replace("__ARGS__", json.dumps({"intent": intent})),
            timeout_sec=30.0,
        )
        assert listed.get("ready") is True, json.dumps(listed, ensure_ascii=False)
        assert listed.get("stored") is True, f"localStorage missing comment: {listed}"

        # T4: reload -> the comment survives (persistence proof).
        navigate_mcp_page(client, page, chat_url, timeout_ms=90_000)
        content2 = wait_for_state(client, page, _PORTAL_WITH_TEXT_JS, timeout_sec=120.0)
        assert content2.get("ready") is True, json.dumps(content2, ensure_ascii=False)
        client.evaluate(page, _OPEN_PANEL_JS, timeout_sec=15.0)
        relisted = wait_for_state(
            client,
            page,
            _LIST_READY_JS.replace("__ARGS__", json.dumps({"intent": intent})),
            timeout_sec=30.0,
        )
        assert relisted.get("ready") is True, json.dumps(relisted, ensure_ascii=False)
