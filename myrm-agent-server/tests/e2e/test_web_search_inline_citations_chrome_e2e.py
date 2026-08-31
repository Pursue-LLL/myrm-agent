"""Chrome E2E (READ): web search inline citation rendering via lib/citations SSOT.

Injects an assistant message with sources + 【N】/[N] markers and verifies:
- prose markers become clickable <citation> elements
- fenced code keeps literal markers (maskCode path)
- Sources action bar button appears
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_INJECT_WEB_CITATION_MESSAGE_JS = """(() => {
  const chatStore = window.__myrmChatStore;
  if (!chatStore?.getState || !chatStore.setState) {
    return { ok: false, err: 'chat-store-missing' };
  }
  const chatId = 'e2e-web-inline-citations';
  const message = {
    messageId: 'e2e-web-inline-citations-assistant',
    chatId,
    createdAt: new Date(),
    content:
      '欧盟 AI 法案已于 2025 年生效【1】。English growth was 5% [2].\\n\\n```python\\n# example marker 【3】 and arr[2]\\n```',
    role: 'assistant',
    sources: [
      {
        index: 1,
        type: 'web_search',
        url: 'https://example.com/eu-ai-act',
        title: 'EU AI Act',
      },
      {
        index: 2,
        type: 'web_search',
        url: 'https://example.com/growth',
        title: 'Growth report',
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
  return { ok: true, chatId, messageCount: 1 };
})()"""

_CITATION_RENDER_READY_JS = """(() => {
  const citations = Array.from(document.querySelectorAll('citation'));
  const pre = document.querySelector('pre');
  const preText = pre?.textContent || '';
  const buttons = Array.from(document.querySelectorAll('button'));
  const sourcesBtn = buttons.find((btn) => {
    const label = (btn.textContent || '').trim();
    const aria = btn.getAttribute('aria-label') || '';
    return /Sources|来源/i.test(label) || /sources/i.test(aria);
  });
  const proseCitation = citations.find((el) => el.getAttribute('data-num') === '1');
  const englishCitation = citations.find((el) => el.getAttribute('data-num') === '2');
  return {
    ready:
      citations.length >= 2 &&
      Boolean(proseCitation) &&
      Boolean(englishCitation) &&
      /【3】/.test(preText) &&
      /arr\\[2\\]/.test(preText) &&
      Boolean(sourcesBtn),
    citationCount: citations.length,
    hasProseCitation: Boolean(proseCitation),
    hasEnglishCitation: Boolean(englishCitation),
    codeHasFullwidthMarker: /【3】/.test(preText),
    codeHasHalfwidthIndex: /arr\\[2\\]/.test(preText),
    hasSourcesButton: Boolean(sourcesBtn),
    sourcesLabel: sourcesBtn?.textContent?.trim() || null,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_web_search_inline_citations_render_chrome_e2e() -> None:
    """Injected web sources render inline citations without mutating code blocks."""
    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=90_000) as (client, page):
        injected = client.evaluate(page, _INJECT_WEB_CITATION_MESSAGE_JS, timeout_sec=15.0)
        assert isinstance(injected, dict), injected
        assert injected.get("ok") is True, json.dumps(injected, ensure_ascii=False)

        ready = wait_for_state(client, page, _CITATION_RENDER_READY_JS, timeout_sec=45.0)
        assert ready.get("ready") is True, ready
