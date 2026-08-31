"""Chrome E2E (READ): web search inline citation rendering via lib/citations SSOT.

Injects an assistant message with sources + 【N】/[N] markers and verifies:
- prose markers become clickable <citation> elements
- fenced code keeps literal markers (maskCode path)
- unified Evidence action bar button appears
"""

from __future__ import annotations

import json

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

_CHAT_ID = "e2e-web-inline-citations"

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

_INJECT_WEB_CITATION_MESSAGE_JS = f"""(() => {{
  const chatStore = window.__myrmChatStore;
  if (!chatStore?.getState || !chatStore.setState) {{
    return {{ ok: false, err: 'chat-store-missing' }};
  }}
  const chatId = {json.dumps(_CHAT_ID)};
  const message = {{
    messageId: 'e2e-web-inline-citations-assistant',
    chatId,
    createdAt: new Date(),
    content:
      '欧盟 AI 法案已于 2025 年生效【1】。English growth was 5% [2].\\n\\n```python\\n# example marker 【3】 and arr[2]\\n```',
    role: 'assistant',
    sources: [
      {{
        index: 1,
        type: 'web_search',
        url: 'https://example.com/eu-ai-act',
        title: 'EU AI Act',
      }},
      {{
        index: 2,
        type: 'web_search',
        url: 'https://example.com/growth',
        title: 'Growth report',
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
  const domMessage = document.querySelector('[data-message-id]');
  return {
    ready: Boolean(assistant) && Boolean(domMessage),
    hasAssistantShell: Boolean(assistant),
    hasDomMessage: Boolean(domMessage),
  };
})()"""

_CITATION_RENDER_READY_JS = """(() => {
  const messageEl = document.querySelector('[data-message-id="e2e-web-inline-citations-assistant"]');
  const pre = messageEl?.querySelector('pre');
  const preText = pre?.textContent || '';
  const citationTriggers = Array.from(
    messageEl?.querySelectorAll('a.bg-secondary, span.bg-secondary') ?? [],
  );
  const hasCitation1 = citationTriggers.some((el) => (el.textContent || '').trim() === '1');
  const hasCitation2 = citationTriggers.some((el) => (el.textContent || '').trim() === '2');
  const proseText = messageEl?.textContent || '';
  const buttons = Array.from(document.querySelectorAll('button'));
  const evidenceBtn = buttons.find((btn) => {
    const label = (btn.textContent || '').trim();
    const aria = btn.getAttribute('aria-label') || '';
    return /依据\\s*\\d+|Evidence\\s*\\d+/i.test(label) ||
      /sources and memories|依据/.test(aria);
  });
  return {
    ready:
      Boolean(messageEl) &&
      hasCitation1 &&
      hasCitation2 &&
      /【3】/.test(preText) &&
      /arr\\[2\\]/.test(preText) &&
      !/生效【1】/.test(proseText) &&
      Boolean(evidenceBtn),
    citationTriggerCount: citationTriggers.length,
    hasCitation1,
    hasCitation2,
    codeHasFullwidthMarker: /【3】/.test(preText),
    codeHasHalfwidthIndex: /arr\\[2\\]/.test(preText),
    hasEvidenceButton: Boolean(evidenceBtn),
    evidenceLabel: evidenceBtn?.textContent?.trim() || null,
    proseStillHasFullwidthMarker: /生效【1】/.test(proseText),
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.timeout(240)
def test_web_search_inline_citations_render_chrome_e2e() -> None:
    """Injected web sources render inline citations without mutating code blocks."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/", timeout_sec=45.0)
    chat_url = f"{ui_url}/{_CHAT_ID}"
    with open_mcp_page(chat_url, request_timeout_sec=300.0) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)

        injected = client.evaluate(page, _INJECT_WEB_CITATION_MESSAGE_JS, timeout_sec=15.0)
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

        ready = wait_for_state(
            client,
            page,
            _CITATION_RENDER_READY_JS,
            timeout_sec=60.0,
            page_url=chat_url,
        )
        assert ready.get("ready") is True, ready
