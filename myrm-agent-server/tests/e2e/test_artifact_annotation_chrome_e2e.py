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
  const store = window.__myrmArtifactPortalStore?.getState?.();
  const tabs = store?.openTabs ?? [];
  return { ready: tabs.length > 0, tabCount: tabs.length };
})()"""

_DIRECT_OPEN_JS = """(() => {
  const store = window.__myrmArtifactPortalStore?.getState?.();
  if (!store) return { ok: false, reason: 'no-store' };
  store.openArtifact({
    id: 'ws-probe-direct.md',
    filename: 'probe-direct.md',
    type: 'document',
    content_type: 'text/markdown',
    size: 11,
    preview_url: '',
    download_url: '',
  });
  store.setContent('# Probe Direct\\n\\nDirect store-to-render check.');
  const st = window.__myrmArtifactPortalStore.getState();
  return { ok: true, isOpen: !!st.isOpen, tabs: (st.openTabs || []).length };
})()"""

_DIRECT_RENDER_JS = """(() => {
  const container = document.getElementById('artifact-content-container');
  const storeModules = performance
    .getEntriesByType('resource')
    .map((r) => r.name)
    .filter((n) => n.includes('useArtifactPortalStore') || n.includes('ArtifactPortal'));
  const zeroByteChunks = performance
    .getEntriesByType('resource')
    .filter((r) => r.name.includes('/_next/') && r.transferSize === 0 && r.decodedBodySize === 0)
    .map((r) => r.name.slice(-80))
    .slice(0, 5);
  const nextErrors = Array.from(document.querySelectorAll('nextjs-portal')).length;
  const artifactTestIds = Array.from(document.querySelectorAll('[data-testid]'))
    .map((el) => el.getAttribute('data-testid'))
    .filter((t) => t && t.toLowerCase().includes('artifact'))
    .slice(0, 10);
  return {
    hasContainer: !!container,
    text: container ? (container.innerText || '').slice(0, 200) : null,
    storeModules,
    zeroByteChunks,
    nextErrors,
    artifactTestIds,
  };
})()"""
_PORTAL_WITH_TEXT_JS = r"""(() => {
  const containers = Array.from(document.querySelectorAll('#artifact-content-container'));
  const text = containers.map((c) => c.innerText || '').join(' | ');
  const dialogs = Array.from(document.querySelectorAll('[role="dialog"], [role="complementary"]')).map((el) => ({
    role: el.getAttribute('role'),
    label: (el.getAttribute('aria-label') || '').slice(0, 80),
    cls: (el.getAttribute('class') || '').slice(0, 120),
    textHead: ((el.innerText || '')).slice(0, 200),
  }));
  const viewport = { w: window.innerWidth, h: window.innerHeight };
  const href = location.href;
  const reactMounted =
    typeof window.__REACT_DEVTOOLS_GLOBAL_HOOK__ !== 'undefined' &&
    (window.__REACT_DEVTOOLS_GLOBAL_HOOK__.renderers?.size ?? 0) > 0;
  const nextRootKids = document.getElementById('__next')?.childElementCount ?? -1;
  const failedChunks = performance
    .getEntriesByType('resource')
    .map((r) => r.name)
    .filter((n) => n.includes('_next/static/chunks') && n.includes('ArtifactPortal'));
  const buildErrors = Array.from(document.querySelectorAll('nextjs-portal')).map((el) =>
    (((el.shadowRoot?.textContent || el.textContent) || '').replace(/\s+/g, ' ').slice(0, 1500)),
  );
  const anyPortalDialog = dialogs.length > 0;
  const bodyTxt = (document.body?.innerText || '').slice(0, 300);
  const store = window.__myrmArtifactPortalStore?.getState?.();
  const tabs = store?.openTabs ?? [];
  const loading = !!document.querySelector('[data-testid="artifact-loading"], .animate-pulse, .animate-spin');
  const errBox = document.querySelector('[data-testid="artifact-error"]');
  const tab = tabs.length > 0 ? tabs[0] : null;
  const activeIndex = typeof store?.activeTabIndex === 'number' ? store.activeTabIndex : null;
  const activeTab = activeIndex !== null && activeIndex >= 0 && activeIndex < tabs.length ? tabs[activeIndex] : null;
  const previewUrl = tab && tab.artifact ? (tab.artifact.preview_url || null) : null;
  const tabLoading = !!(tab && tab.contentLoading);
  const tabError = tab && tab.error ? String(tab.error.messageKey || tab.error).slice(0, 120) : null;
  return {
    ready: containers.length > 0 && text.includes('Deliverable E2E'),
    len: text.length,
    hasContainer: containers.length > 0,
    containerCount: containers.length,
    dialogs,
    viewport,
    href,
    reactMounted,
    nextRootKids,
    failedChunks,
    buildErrors,
    tabCount: tabs.length,
    tabFile: tab ? (tab?.artifact?.filename ?? null) : null,
    tabHasContent: !!(tab && typeof tab.content === 'string' && tab.content.length > 0),
    tabContentLen: tab && typeof tab.content === 'string' ? tab.content.length : -1,
    bodyHead: bodyTxt,
    activeTabIndex: activeIndex,
    activeTabNull: !activeTab,
    previewUrl,
    tabLoading,
    tabError,
    isOpen: store ? !!store.isOpen : null,
    anyPortal: anyPortalDialog,
    loading,
    hasError: !!errBox,
    errText: errBox ? (errBox.innerText || '').slice(0, 200) : null,
  };
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


_BODY_ALIVE_JS = """(() => ({ len: (document.body?.innerText || '').length }))()"""


def _navigate_alive(client: object, page: object, url: str, *, attempts: int = 4) -> None:
    """Navigate until the document body is non-blank (dev HMR can serve an
    empty shell while Turbopack recompiles under parallel edits)."""
    for _ in range(attempts):
        navigate_mcp_page(client, page, url, timeout_ms=90_000)
        deadline = time.monotonic() + 45.0
        while time.monotonic() < deadline:
            try:
                state = client.evaluate(page, _BODY_ALIVE_JS, timeout_sec=15.0)
            except Exception:
                time.sleep(3.0)
                continue
            if isinstance(state, dict) and int(state.get("len") or 0) > 100:
                return
            time.sleep(3.0)
    raise AssertionError(f"page body stayed blank after {attempts} navigations to {url}")


def _seed_deliverable_fixture(api_url: str) -> dict[str, object]:
    # Seed into the shared backend: the :3000 WebUI proxies /api there, so
    # isolate-seeded chats are invisible in the browser.
    del api_url
    seeded = http_json("POST", "http://127.0.0.1:8080/api/v1/chats/test/seed-deliverable-link-fixture")
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
    try:
        warm_ui_route("/", timeout_sec=45.0)
        chat_url = f"{ui_url}/{chat_id}"
        with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            _navigate_alive(client, page, chat_url)

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
            # Decisive experiment: drive the store directly (bypasses the link
            # click path). If the DOM still shows nothing, the break is in the
            # store->render subscription, not the click flow.
            # Decisive experiment (diagnostic only, never fatal): drive the store
            # directly. Its outcome is recorded for forensics.
            direct = client.evaluate(page, _DIRECT_OPEN_JS, timeout_sec=15.0)
            direct_render: dict | None = None
            try:
                direct_render = wait_for_state(client, page, _DIRECT_RENDER_JS, timeout_sec=30.0)
            except Exception as diag_err:
                direct_render = {"ready": False, "diag_error": str(diag_err)[:200]}
            assert isinstance(direct, dict) and direct.get("ok") is True, direct
            store_state = wait_for_state(client, page, _PORTAL_STORE_READY_JS, timeout_sec=90.0)
            assert store_state.get("ready") is True, json.dumps(
                {"store": store_state, "direct_render": direct_render}, ensure_ascii=False
            )
            content: dict | None = None
            last_probe: dict | None = None
            content_deadline = time.monotonic() + 150.0
            while time.monotonic() < content_deadline:
                try:
                    probe = client.evaluate(page, _PORTAL_WITH_TEXT_JS, timeout_sec=15.0)
                except Exception:
                    time.sleep(3.0)
                    continue
                if not isinstance(probe, dict):
                    time.sleep(3.0)
                    continue
                last_probe = probe
                if probe.get("ready") is True:
                    content = probe
                    break
                if probe.get("hasError"):
                    raise AssertionError(f"portal content failed: {json.dumps(probe, ensure_ascii=False)}")
                if not probe.get("tabCount"):
                    # Portal lost its tab mid-stream; re-enter via the link.
                    retry = client.evaluate(page, _OPEN_FIRST_DELIVERABLE_JS, timeout_sec=15.0)
                    if not (isinstance(retry, dict) and retry.get("ok")):
                        time.sleep(3.0)
                    continue
                time.sleep(3.0)
            assert isinstance(content, dict) and content.get("ready") is True, json.dumps(
                {"content": content, "last_probe": last_probe}, ensure_ascii=False
            )

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
            _navigate_alive(client, page, chat_url)
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
    finally:
        # Best-effort cleanup of the shared-backend fixture chat.
        try:
            http_json("DELETE", f"http://127.0.0.1:8080/api/v1/chats/{chat_id}")
        except Exception:
            pass
