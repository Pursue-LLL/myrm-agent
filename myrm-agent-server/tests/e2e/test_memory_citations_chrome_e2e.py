"""Real Chrome MCP E2E for memory settings opt-in and unified evidence UI."""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state, warm_ui_route
from tests.support.chrome_memory_settings_e2e import (
    ENABLE_MEMORY_JS,
    SETTINGS_SHELL_READY_JS,
    conversation_search_toggle_js,
)

_INJECT_EVIDENCE_MESSAGE_JS = """(() => {
  const chatStore = window.__myrmChatStore;
  if (!chatStore?.getState || !chatStore.setState) {
    return { ok: false, err: 'chat-store-missing' };
  }
  const chatId = 'e2e-memory-citations-ui';
  const message = {
    messageId: 'e2e-memory-citations-assistant',
    chatId,
    createdAt: new Date(),
    content: 'The brand primary color is blue.',
    role: 'assistant',
    citedMemoryRefs: [
      {
        id: 'mem-e2e-brand-color',
        content: 'Brand primary color: blue',
        type: 'semantic',
      },
    ],
    sources: [
      {
        index: 1,
        type: 'conversation_history',
        title: 'Prior design chat',
        summary: 'We agreed on blue as the brand color last week.',
      },
    ],
  };
  chatStore.setState({
    chatId,
    messages: [message],
    loading: false,
    isMessagesLoaded: true,
    messageAppeared: true,
    notFound: false,
    loadError: false,
  });
  return { ok: true, chatId, path: location.pathname, messageCount: 1 };
})()"""

_EVIDENCE_BUTTON_READY_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const evidenceBtn = buttons.find((btn) => {
    const label = (btn.textContent || '').trim();
    const aria = btn.getAttribute('aria-label') || '';
    return /依据\\s*\\d+|Evidence\\s*\\d+/i.test(label) ||
      /sources and memories|依据/.test(aria);
  });
  return {
    ready: Boolean(evidenceBtn),
    label: evidenceBtn?.textContent?.trim() || null,
    aria: evidenceBtn?.getAttribute('aria-label') || null,
  };
})()"""

_OPEN_EVIDENCE_SHEET_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const evidenceBtn = buttons.find((btn) => {
    const label = (btn.textContent || '').trim();
    return /依据\\s*\\d+|Evidence\\s*\\d+/i.test(label);
  });
  if (!evidenceBtn) {
    return { clicked: false };
  }
  evidenceBtn.click();
  return { clicked: true, label: evidenceBtn.textContent?.trim() || '' };
})()"""

_EVIDENCE_SHEET_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Sources & Memories|依据与记忆/.test(text);
  const hasMemories = /Memories|记忆/.test(text);
  const hasSources = /Other sources|其他来源/.test(text);
  const hasMemoryBody = /Brand primary color|blue/i.test(text);
  const hasHistoryBody = /Prior design chat|brand color/i.test(text);
  return {
    ready: hasTitle && hasMemories && hasSources && hasMemoryBody && hasHistoryBody,
    hasTitle,
    hasMemories,
    hasSources,
    hasMemoryBody,
    hasHistoryBody,
    sample: text.slice(0, 500),
  };
})()"""


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
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
            raw = client.evaluate(page, conversation_search_toggle_js(target_checked=True), timeout_sec=10.0)
            toggled = raw if isinstance(raw, dict) else {"value": raw}
            if toggled.get("ok") is True:
                break
            time.sleep(0.5)
        assert toggled.get("ok") is True, json.dumps(toggled, ensure_ascii=False)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.timeout(240)
def test_memory_citations_evidence_button_opens_unified_sheet() -> None:
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=90_000) as (client, page):
        injected = client.evaluate(page, _INJECT_EVIDENCE_MESSAGE_JS, timeout_sec=15.0)
        assert isinstance(injected, dict), injected
        assert injected.get("ok") is True, json.dumps(injected, ensure_ascii=False)

        button = wait_for_state(client, page, _EVIDENCE_BUTTON_READY_JS, timeout_sec=45.0)
        assert button.get("ready") is True, button

        opened = client.evaluate(page, _OPEN_EVIDENCE_SHEET_JS, timeout_sec=10.0)
        assert isinstance(opened, dict), opened
        assert opened.get("clicked") is True, opened

        sheet = wait_for_state(client, page, _EVIDENCE_SHEET_READY_JS, timeout_sec=30.0)
        assert sheet.get("ready") is True, sheet
