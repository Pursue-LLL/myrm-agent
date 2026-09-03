"""Real Chrome MCP E2E for memory settings opt-in and unified evidence UI."""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)
from tests.support.chrome_memory_settings_e2e import (
    ENABLE_MEMORY_JS,
    SETTINGS_SHELL_READY_JS,
    conversation_search_toggle_js,
)

_CHAT_ID = "e2e-memory-citations-ui"

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

_INJECT_EVIDENCE_MESSAGE_JS = f"""(() => {{
  const chatStore = window.__myrmChatStore;
  if (!chatStore?.getState || !chatStore.setState) {{
    return {{ ok: false, err: 'chat-store-missing' }};
  }}
  const chatId = {json.dumps(_CHAT_ID)};
  const message = {{
    messageId: 'e2e-memory-citations-assistant',
    chatId,
    createdAt: new Date(),
    content: 'The brand primary color is blue.',
    role: 'assistant',
    citedMemoryRefs: [
      {{
        id: 'mem-e2e-brand-color',
        content: 'Brand primary color: blue',
        type: 'semantic',
      }},
    ],
    sources: [
      {{
        index: 1,
        type: 'conversation_history',
        title: 'Prior design chat',
        summary: 'We agreed on blue as the brand color last week.',
      }},
    ],
  }};
  chatStore.setState({{
    chatId,
    messages: [message],
    loading: false,
    isMessagesLoaded: true,
    messageAppeared: true,
    notFound: false,
    loadError: false,
  }});
  return {{ ok: true, chatId, path: location.pathname, messageCount: 1 }};
}})()"""

_ASSISTANT_MESSAGE_READY_JS = """(() => {
  const assistant = document.querySelector('[data-test-id="assistant-message"]');
  const domMessage = document.querySelector('[data-message-id="e2e-memory-citations-assistant"]');
  return {
    ready: Boolean(assistant) && Boolean(domMessage),
    hasAssistantShell: Boolean(assistant),
    hasDomMessage: Boolean(domMessage),
  };
})()"""

_ENSURE_INJECT_AND_OPEN_SHEET_JS = """(() => {
  const chatStore = window.__myrmChatStore;
  if (!chatStore?.getState || !chatStore.setState) {
    return { ready: false, err: 'chat-store-missing' };
  }
  const state = chatStore.getState();
  const hasInjected = (state.messages || []).some(
    (m) => m?.messageId === 'e2e-memory-citations-assistant',
  );
  if (!hasInjected) {
    const chatId = 'e2e-memory-citations-ui';
    chatStore.setState({
      chatId,
      messages: [{
        messageId: 'e2e-memory-citations-assistant',
        chatId,
        createdAt: new Date(),
        content: 'The brand primary color is blue.',
        role: 'assistant',
        citedMemoryRefs: [{
          id: 'mem-e2e-brand-color',
          content: 'Brand primary color: blue',
          type: 'semantic',
        }],
        sources: [{
          index: 1,
          type: 'conversation_history',
          title: 'Prior design chat',
          summary: 'We agreed on blue as the brand color last week.',
        }],
      }],
      loading: false,
      isMessagesLoaded: true,
      messageAppeared: true,
      notFound: false,
      loadError: false,
    });
  }

  const findEvidenceBtn = () => Array.from(document.querySelectorAll('button')).find((btn) => {
    const label = (btn.textContent || '').trim();
    const aria = btn.getAttribute('aria-label') || '';
    return /依据\\s*\\d+|Evidence\\s*\\d+/i.test(label) ||
      /sources and memories|依据与记忆|条依据/i.test(aria);
  });

  let evidenceBtn = findEvidenceBtn();
  if (!evidenceBtn) {
    return { ready: false, err: 'evidence-button-missing', reinjected: !hasInjected };
  }

  const dialogOpen = () => {
    const dialog = document.querySelector('[role="dialog"]');
    if (!dialog) {
      return null;
    }
    const text = dialog.innerText || '';
    const copyBtns = Array.from(dialog.querySelectorAll('button')).filter((b) => {
      const aria = b.getAttribute('aria-label') || '';
      const title = b.getAttribute('title') || '';
      return /Markdown/i.test(aria) || /Markdown/i.test(title);
    });
    return {
      hasTitle: /Sources & Memories|依据与记忆/.test(text),
      hasMemories: /Memories|记忆/.test(text),
      hasSources: /Other sources|其他来源/.test(text),
      hasMemoryBody: /Brand primary color/i.test(text),
      hasHistoryBody: /Prior design chat/i.test(text),
      hasCopyMarkdown: copyBtns.length > 0,
      copyBtnCount: copyBtns.length,
      sample: text.slice(0, 400),
    };
  };

  let sheet = dialogOpen();
  if (!(sheet && sheet.hasTitle && sheet.hasMemoryBody && sheet.hasHistoryBody)) {
    evidenceBtn.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
    evidenceBtn.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    evidenceBtn.click();
    sheet = dialogOpen();
  }

  if (!sheet) {
    return { ready: false, err: 'dialog-missing', clicked: true, label: evidenceBtn.textContent?.trim() };
  }
  return {
    ready:
      sheet.hasTitle &&
      sheet.hasMemories &&
      sheet.hasSources &&
      sheet.hasMemoryBody &&
      sheet.hasHistoryBody &&
      sheet.hasCopyMarkdown &&
      sheet.copyBtnCount >= 2,
    ...sheet,
    clicked: true,
    reinjected: !hasInjected,
    label: evidenceBtn.textContent?.trim() || null,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_memory_settings_conversation_search_toggle() -> None:
    warm_ui_route("/settings/memory")
    ui_base = get_e2e_ui_url()
    with open_mcp_page(ui_base, timeout_ms=90_000) as (client, page):
        client.navigate(page, f"{ui_base}/settings/memory", timeout_ms=90_000)
        shell = wait_for_state(client, page, SETTINGS_SHELL_READY_JS, timeout_sec=90.0)
        assert shell.get("ready") is True, shell

        memory_on = client.evaluate(page, ENABLE_MEMORY_JS, timeout_sec=15.0)
        assert isinstance(memory_on, dict) and memory_on.get("ok") is True, memory_on
        time.sleep(1.0)

        toggled: dict[str, object] = {}
        deadline = time.monotonic() + 30.0
        while time.monotonic() < deadline:
            raw = client.evaluate(
                page,
                conversation_search_toggle_js(target_checked=True),
                timeout_sec=10.0,
            )
            toggled = raw if isinstance(raw, dict) else {"value": raw}
            if toggled.get("ok") is True:
                break
            time.sleep(0.5)
        assert toggled.get("ok") is True, json.dumps(toggled, ensure_ascii=False)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="live_shpoib",
)
@pytest.mark.timeout(240)
def test_memory_citations_evidence_button_opens_unified_sheet() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/", timeout_sec=45.0)
    chat_url = f"{ui_url}/{_CHAT_ID}"
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)

        injected = client.evaluate(page, _INJECT_EVIDENCE_MESSAGE_JS, timeout_sec=15.0)
        assert isinstance(injected, dict), injected
        assert injected.get("ok") is True, json.dumps(injected, ensure_ascii=False)

        client.evaluate(page, _SCROLL_MESSAGES_JS, timeout_sec=10.0)

        message_ready = wait_for_state(
            client,
            page,
            _ASSISTANT_MESSAGE_READY_JS,
            timeout_sec=60.0,
            page_url=chat_url,
        )
        assert message_ready.get("ready") is True, message_ready

        # Do NOT pass page_url here: wait_for_state heal/reload would wipe injected store.
        sheet = wait_for_state(
            client,
            page,
            _ENSURE_INJECT_AND_OPEN_SHEET_JS,
            timeout_sec=45.0,
        )
        assert sheet.get("ready") is True, sheet
