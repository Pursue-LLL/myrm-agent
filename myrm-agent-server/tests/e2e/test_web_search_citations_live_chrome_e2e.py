"""Chrome LIVE E2E: general agent web_search → sources SSE → inline citation UI."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    open_mcp_page_async,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once
from tests.support.test_secrets import resolve_test_env

_TURN_WAIT_SEC = 360.0

_PROMPT = (
    "请必须使用 web_search 工具搜索「OpenCode AI」，用一句话总结搜索结果，正文中必须用【1】标注引用来源，末尾单独一行写 CITE_OK。"
)

_FAST_PROMPT = "请搜索「Python 3.14 新特性」，用一句话总结，正文中必须用【1】标注引用，末尾单独一行写 CITE_OK。"

_PREP_GENERAL_AGENT_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ready: false, err: 'no-bridge' };
  await bridge.ensureProviders?.();
  bridge.setWorkflowMode?.(false);
  bridge.setActionMode?.('agent');
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  bridge.setSseCaptureMessageId?.(null);
  bridge.setCurrentBuiltinTools?.(['web_search']);
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  if (typeof bridge.pinBasicModelForE2e === 'function') {
    await bridge.pinBasicModelForE2e({ preserveActionMode: true });
  }
  if (typeof bridge.syncSearchServicesFromE2eApi === 'function') {
    await bridge.syncSearchServicesFromE2eApi();
  }
  const debug = bridge.debugProviderState?.() ?? null;
  const search = bridge.debugSearchState?.() ?? null;
  const sendReady = bridge.isSendReady?.() === true;
  const hasInput = !!document.querySelector('[data-chat-input]');
  return {
    ready: hasInput && sendReady && !!debug?.selection && bridge.isWorkflowMode?.() !== true
      && Number(search?.enabledCount ?? 0) > 0,
    sendReady,
    hasInput,
    workflowMode: bridge.isWorkflowMode?.() ?? null,
    searchEnabled: Number(search?.enabledCount ?? 0),
    selection: debug?.selection ?? null,
  };
})()"""

_PREP_FAST_SEARCH_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ready: false, err: 'no-bridge' };
  await bridge.ensureProviders?.();
  bridge.setWorkflowMode?.(false);
  bridge.setActionMode?.('fast');
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  bridge.setSseCaptureMessageId?.(null);
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  if (typeof bridge.pinLiteModelForE2e === 'function') {
    await bridge.pinLiteModelForE2e({ preserveActionMode: true });
  } else if (typeof bridge.pinBasicModelForE2e === 'function') {
    await bridge.pinBasicModelForE2e({ preserveActionMode: true });
  }
  bridge.setActionMode?.('fast');
  if (typeof bridge.syncSearchServicesFromE2eApi === 'function') {
    await bridge.syncSearchServicesFromE2eApi();
  }
  const debug = bridge.debugProviderState?.() ?? null;
  const search = bridge.debugSearchState?.() ?? null;
  const sendReady = bridge.isSendReady?.() === true;
  const hasInput = !!document.querySelector('[data-chat-input]');
  const mode = bridge.getActionMode?.() ?? null;
  return {
    ready: hasInput && sendReady && !!debug?.selection && mode === 'fast'
      && Number(search?.enabledCount ?? 0) > 0,
    sendReady,
    hasInput,
    actionMode: mode,
    searchEnabled: Number(search?.enabledCount ?? 0),
    selection: debug?.selection ?? null,
  };
})()"""

_CITATION_LIVE_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  if (!store) {
    return { ready: false, reason: 'no-store' };
  }
  const assistants = (store.messages ?? []).filter((m) => m?.role === 'assistant');
  const last = assistants[assistants.length - 1];
  if (!last) {
    return { ready: false, reason: 'no-assistant', loading: store.loading };
  }
  const sources = Array.isArray(last.sources) ? last.sources : [];
  const content = String(last.content || '');
  const messageEl = (() => {
    const nodes = document.querySelectorAll(`[data-message-id="${last.messageId}"]`);
    return nodes.length > 0 ? nodes[nodes.length - 1] : null;
  })();
  const citationTriggers = Array.from(
    messageEl?.querySelectorAll('a, span') ?? [],
  ).filter((el) => {
    const text = (el.textContent || '').trim();
    if (!/^\\d+$/.test(text)) {
      return false;
    }
    const cls = typeof el.className === 'string' ? el.className : '';
    return cls.includes('bg-secondary') || cls.includes('secondary') || cls.includes('px-1');
  });
  const secondaryClassHits = messageEl
    ? messageEl.querySelectorAll('[class*="secondary"], [class*="px-1"]').length
    : 0;
  const proseHasFullwidth = /【\\d+】/.test(messageEl?.textContent || '');
  const digitOnlyNodes = Array.from(messageEl?.querySelectorAll('a, span') ?? [])
    .filter((el) => /^\\d+$/.test((el.textContent || '').trim()))
    .map((el) => ({
      tag: el.tagName,
      text: (el.textContent || '').trim(),
      cls: typeof el.className === 'string' ? el.className.slice(0, 80) : '',
    }))
    .slice(0, 8);
  const buttons = Array.from(document.querySelectorAll('button'));
  const evidenceBtn = buttons.find((btn) => {
    const label = (btn.textContent || '').trim();
    const aria = btn.getAttribute('aria-label') || '';
    return /依据\\s*\\d+|Evidence\\s*\\d+/i.test(label) ||
      /sources and memories|依据/.test(aria);
  });
  const hasCiteOk = /CITE_OK/i.test(content);
  const hasInlineBadge = citationTriggers.length > 0;
  const hasCitationMarker = /【\\d+】/.test(content) || /\\[\\d+\\]/.test(content);
  const sourceIndexes = sources.map((s) => s?.index ?? null);
  const progressTools = (last.progressSteps || [])
    .map((s) => s?.tool_name || s?.title || s?.label || '')
    .filter(Boolean)
    .slice(0, 12);
  return {
    ready:
      !store.loading &&
      sources.length > 0 &&
      Boolean(evidenceBtn) &&
      hasCiteOk &&
      hasInlineBadge &&
      hasCitationMarker &&
      !proseHasFullwidth,
    loading: store.loading,
    sourceCount: sources.length,
    sourceIndexes,
    sourceIndexTypes: sources.slice(0, 3).map((s) => typeof s?.index),
    citationBadgeCount: citationTriggers.length,
    secondaryClassHits,
    proseHasFullwidth,
    digitOnlyNodes,
    hasMessageEl: Boolean(messageEl),
    hasEvidenceButton: Boolean(evidenceBtn),
    hasCiteOk,
    hasInlineBadge,
    hasCitationMarker,
    progressTools,
    assistantCount: assistants.length,
    messageId: last.messageId || null,
    contentSample: content.slice(0, 400),
    evidenceLabel: evidenceBtn?.textContent?.trim() || null,
  };
})()"""


def _ensure_search_services(api_url: str) -> None:
    current = fetch_config_value("searchServices", api_url=api_url)
    configs = current.get("searchServiceConfigs")
    if isinstance(configs, list) and configs:
        return
    search_service = resolve_test_env("SEARCH_SERVICE", "tavily") or "tavily"
    api_key = resolve_test_env("TAVILY_API_KEY") or resolve_test_env("SEARCH_API_KEY", "test-tavily-key")
    item: dict[str, object] = {
        "id": f"e2e-search-{uuid.uuid4().hex[:8]}",
        "name": "E2E Search",
        "enabled": True,
        "priority": 1,
        "search_service": search_service,
        "api_key": api_key,
        "createdAt": int(time.time() * 1000),
    }
    put_config_value(
        "searchServices",
        {"searchServiceConfigs": [item]},
        api_url=api_url,
    )


_SCROLL_ASSISTANT_INTO_VIEW_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const assistants = (store?.messages ?? []).filter((m) => m?.role === 'assistant');
  const last = assistants[assistants.length - 1];
  const el = last?.messageId
    ? document.querySelector(`[data-message-id="${last.messageId}"]`)
    : null;
  if (el && typeof el.scrollIntoView === 'function') {
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
  }
  return { ok: true, hasEl: Boolean(el), messageId: last?.messageId ?? null };
})()"""


_PIN_FAST_BEFORE_SEND_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setActionMode) {
    return { ok: false, err: 'no-setActionMode' };
  }
  bridge.setActionMode('fast');
  return { ok: true, actionMode: bridge.getActionMode?.() ?? null };
})()"""


async def _wait_citation_ui(chat: McpChatSession, *, timeout_sec: float) -> dict[str, object]:
    await chat.evaluate(_SCROLL_ASSISTANT_INTO_VIEW_JS, await_promise=False)
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict[str, object] = {}
    while asyncio.get_event_loop().time() < deadline:
        await chat.evaluate(_SCROLL_ASSISTANT_INTO_VIEW_JS, await_promise=False)
        raw = await chat.evaluate(_CITATION_LIVE_READY_JS, await_promise=False)
        last = raw if isinstance(raw, dict) else {"raw": raw}
        if last.get("ready") is True:
            return last
        await asyncio.sleep(3.0)
    return last


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_general_agent_web_search_citations_live_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Lane-C: general agent web_search → metadata.sources → Evidence + inline cite UI."""
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    seed_live_e2e_providers(api_base)
    _ensure_search_services(api_base)

    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/", timeout_sec=90.0)

    session = await open_mcp_page_async(
        ui_base,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    )
    try:
        chat = McpChatSession(session.client, session.page)
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
        prep = await chat.evaluate(_PREP_GENERAL_AGENT_JS, await_promise=True)
        assert isinstance(prep, dict) and prep.get("ready") is True, prep
        await chat.click_new_chat()
        prep2 = await chat.evaluate(_PREP_GENERAL_AGENT_JS, await_promise=True)
        assert isinstance(prep2, dict) and prep2.get("ready") is True, prep2
        heartbeat_once()

        await chat.send_message(_PROMPT, _PROMPT)
        turn = await chat.wait_turn_done(_PROMPT, timeout_sec=_TURN_WAIT_SEC)
        print(f"E2E_WEB_CITE_TURN_DONE: {json.dumps(turn, ensure_ascii=False)[:800]}", flush=True)

        ui_state = await _wait_citation_ui(chat, timeout_sec=60.0)
        print(f"E2E_WEB_CITE_UI_STATE: {json.dumps(ui_state, ensure_ascii=False)}", flush=True)
        assert ui_state.get("ready") is True, ui_state
        assert int(ui_state.get("sourceCount") or 0) > 0, ui_state
        assert ui_state.get("hasEvidenceButton") is True, ui_state
        assert int(ui_state.get("citationBadgeCount") or 0) >= 1, ui_state
        assert ui_state.get("hasInlineBadge") is True, ui_state
        assert ui_state.get("hasCitationMarker") is True, ui_state
    finally:
        await session.aclose()


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_fast_search_web_search_citations_live_chrome_e2e(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Lane-C: Fast Search mode → sources SSE → Evidence + clickable inline cite badges."""
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider readiness gate failed — run ./myrm ready --chrome")

    api_base = get_e2e_api_url()
    prepare_e2e_ui_session(api_base)
    seed_live_e2e_providers(api_base)
    _ensure_search_services(api_base)

    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/", timeout_sec=90.0)

    session = await open_mcp_page_async(
        ui_base,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    )
    try:
        chat = McpChatSession(session.client, session.page)
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
        prep = await chat.evaluate(_PREP_FAST_SEARCH_JS, await_promise=True)
        assert isinstance(prep, dict) and prep.get("ready") is True, prep
        await chat.click_new_chat()
        # New chat can reset actionMode; pin fast mode again before send.
        prep2 = await chat.evaluate(_PREP_FAST_SEARCH_JS, await_promise=True)
        assert isinstance(prep2, dict) and prep2.get("ready") is True, prep2
        pinned = await chat.evaluate(_PIN_FAST_BEFORE_SEND_JS, await_promise=False)
        assert isinstance(pinned, dict) and pinned.get("ok") is True and pinned.get("actionMode") == "fast", pinned
        heartbeat_once()

        await chat.send_message(_FAST_PROMPT, _FAST_PROMPT)
        turn = await chat.wait_turn_done(_FAST_PROMPT, timeout_sec=_TURN_WAIT_SEC)
        print(f"E2E_FAST_CITE_TURN_DONE: {json.dumps(turn, ensure_ascii=False)[:800]}", flush=True)

        ui_state = await _wait_citation_ui(chat, timeout_sec=60.0)
        print(f"E2E_FAST_CITE_UI_STATE: {json.dumps(ui_state, ensure_ascii=False)}", flush=True)
        assert ui_state.get("ready") is True, ui_state
        assert int(ui_state.get("sourceCount") or 0) > 0, ui_state
        assert ui_state.get("hasEvidenceButton") is True, ui_state
        assert int(ui_state.get("citationBadgeCount") or 0) >= 1, ui_state
        assert ui_state.get("hasInlineBadge") is True, ui_state
        assert ui_state.get("hasCitationMarker") is True, ui_state
    finally:
        await session.aclose()
