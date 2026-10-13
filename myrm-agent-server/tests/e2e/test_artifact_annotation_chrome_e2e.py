"""Chrome E2E: artifact inline annotations end to end (Lane-B).

Seeded deliverable chat -> open ArtifactPortal -> toggle annotation panel ->
select preview text + intent -> Add -> list shows the comment and localStorage
persists it -> reload -> comment survives -> "Send for revision" dispatches the
review through the real chat path and the live model answers it. No mocks,
isolated namespace; annotations live in the test browser profile only.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_chat_messages,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    navigate_mcp_page,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_chat_send_idle,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402

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

_SEND_REVIEW_JS = """(() => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  // Fast mode needs a search service; revisions are agent turns.
  window.__MYRM_E2E_CHAT__?.setActionMode?.('agent');
  const send = Array.from(document.querySelectorAll('section[aria-label="Artifact annotations"] button'))
    .find((b) => /^(Send for revision|发送审阅|傳送審閱)$/.test((b.textContent || '').trim()));
  if (!send) return { ok: false, reason: 'no-send' };
  if (send.disabled) return { ok: false, reason: 'send-disabled' };
  send.click();
  return { ok: true };
})()"""

_SEND_DIAG_JS = """(() => {
  const toasts = Array.from(document.querySelectorAll('[data-sonner-toast]')).map((el) =>
    (el.innerText || '').slice(0, 200),
  );
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null;
  return { toasts, snap, href: location.href };
})()"""

_SUBMITTED_READY_JS = """((args) => {
  const panel = document.querySelector('section[aria-label="Artifact annotations"]');
  const txt = panel ? (panel.innerText || '') : '';
  const stored = window.localStorage.getItem('myrm.artifact-annotations.v1') || '';
  return {
    ready: /submitted|已送审|已送審/.test(txt) && txt.includes(args.intent),
    hasPanel: !!panel,
    panelText: txt.slice(0, 300),
    storedSubmitted: stored.includes('"status":"submitted"'),
    portalOpen: !!document.getElementById('artifact-content-container'),
  };
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
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-deliverable-link-fixture")
    assert isinstance(seeded, dict)
    return seeded


def _open_deliverable_portal(client: object, page: object) -> dict:
    """Click the seeded deliverable link and wait until the portal renders its text.

    Open tabs are not persisted, so every fresh page load must re-open the portal.
    """
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
    content: dict | None = None
    last_probe: dict | None = None
    content_deadline = time.monotonic() + 330.0
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
    return content


def _message_text(message: dict[str, object]) -> str:
    content = message.get("content") or message.get("message") or ""
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _wait_review_answered(chat_id: str, api_url: str, intent: str, *, known: int, timeout_sec: float = 240.0) -> str:
    """Wait for the dispatched review (a new user message) and the live model's answer to it."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        messages = fetch_chat_messages(chat_id, api_url=api_url)[known:]
        sent = next(
            (i for i, m in enumerate(messages) if m.get("role") == "user" and intent in _message_text(m)),
            None,
        )
        if sent is not None:
            for m in messages[sent + 1 :]:
                text = _message_text(m).strip()
                if m.get("role") == "assistant" and text:
                    return text
        time.sleep(2.0)
    tail = [
        {"role": m.get("role"), "text": _message_text(m)[:160]} for m in fetch_chat_messages(chat_id, api_url=api_url)[known:]
    ]
    pytest.fail(
        f"review was not answered by the model within {timeout_sec}s for chat {chat_id}: {json.dumps(tail, ensure_ascii=False)}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_artifact_annotation_panel_roundtrip_via_ui() -> None:
    """Annotation toggle -> panel -> add comment -> persisted across reload."""
    ui_url = get_e2e_ui_url()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready - run ./myrm ready --chrome")

    intent = "E2E review note: verify this paragraph"
    chat_id = ""
    try:
        warm_ui_route("/")
        with open_mcp_page(f"{ui_url}/", request_timeout_sec=300.0) as (client, page):
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            seeded = _seed_deliverable_fixture(api_url)
            chat_id = str(seeded.get("chat_id") or "")
            assert chat_id.startswith("e2edeliv"), seeded
            chat_url = f"{ui_url}/{chat_id}"
            _navigate_alive(client, page, chat_url)

            # T1: open the seeded deliverable; the portal shows its content.
            _open_deliverable_portal(client, page)

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
            _open_deliverable_portal(client, page)
            client.evaluate(page, _OPEN_PANEL_JS, timeout_sec=15.0)
            relisted = wait_for_state(
                client,
                page,
                _LIST_READY_JS.replace("__ARGS__", json.dumps({"intent": intent})),
                timeout_sec=30.0,
            )
            assert relisted.get("ready") is True, json.dumps(relisted, ensure_ascii=False)

            # T5: Send for revision -> real chat turn -> live model answers -> comment marked submitted.
            known = len(fetch_chat_messages(chat_id, api_url=api_url))
            sent = client.evaluate(page, _SEND_REVIEW_JS, timeout_sec=15.0)
            assert isinstance(sent, dict) and sent.get("ok") is True, sent
            time.sleep(5.0)
            diag = client.evaluate(page, _SEND_DIAG_JS, timeout_sec=15.0)
            try:
                answer = _wait_review_answered(chat_id, api_url, intent, known=known, timeout_sec=180.0)
            except pytest.fail.Exception as exc:
                raise AssertionError(f"{exc} ui_after_send={json.dumps(diag, ensure_ascii=False)}") from exc
            assert len(answer) >= 10, answer
            # sendMessage resolves when the whole turn finishes; only then are comments marked submitted.
            idle_at = time.monotonic()
            wait_for_chat_send_idle(client, page, timeout_sec=240.0)
            try:
                submitted = wait_for_state(
                    client,
                    page,
                    _SUBMITTED_READY_JS.replace("__ARGS__", json.dumps({"intent": intent})),
                    timeout_sec=180.0,
                )
            except AssertionError as exc:
                waited = time.monotonic() - idle_at
                raise AssertionError(f"{exc} answer={answer[:200]!r} waited_sec={waited:.0f}") from exc
            assert submitted.get("ready") is True, json.dumps(submitted, ensure_ascii=False)
    finally:
        # Best-effort cleanup of the fixture chat on the backend it was seeded into.
        if chat_id:
            try:
                http_json("DELETE", f"{api_url}/api/v1/chats/{chat_id}")
            except Exception:
                pass
