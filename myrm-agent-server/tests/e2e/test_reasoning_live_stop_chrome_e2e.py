"""Chrome E2E: live turn + reasoning card + stop-thinking.

The history test proves the persisted card; this one drives a real turn through the composer and
asserts the live contract: whenever the thinking card is on screen its controls meet the 40px hit
target and are localized, and stopping the turn really ends it (the button must not stay stuck).
Model reasoning is non-deterministic, so the thinking-specific assertions apply when the turn
actually produces a reasoning chain; the live turn itself is always asserted end-to-end.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

_PROMPT = "请一步步推理：一个农夫有17只羊，除了9只以外都死了，还剩几只？先列出推理步骤，再给出结论，正文不少于 300 字。"

_ATTACH_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) return { ok: false, reason: 'no-attach' };
  // Do not await: the attach GET stays open for the whole turn and would block CDP evaluate.
  void bridge.attachToChat(CHAT_ID).catch(() => undefined);
  return { ok: true };
})()"""

_SEND_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, reason: 'no-bridge' };
  if (bridge.setActionMode) bridge.setActionMode('agent');
  // Fire-and-forget: sendChatMessage awaits its own completion heuristic (~26s) and would
  // hide the thinking window; the store flips to loading immediately either way.
  void bridge.sendChatMessage(PROMPT).catch(() => undefined);
  return { ok: true };
})()"""

_THINKING_JS = """(() => {
  const stop = document.querySelector('[data-testid="stop-thinking-button"]');
  const card = document.querySelector('[data-testid="reasoning-process-accordion"]');
  const rect = stop?.getBoundingClientRect?.();
  return {
    ready: Boolean(stop),
    stop: rect ? { width: Math.round(rect.width), height: Math.round(rect.height) } : null,
    cardText: card ? card.textContent.slice(0, 120) : null,
  };
})()"""

_STOP_JS = """(() => {
  const stop = document.querySelector('[data-testid="stop-thinking-button"]');
  if (!stop) return { ok: false, reason: 'stop-missing' };
  stop.click();
  return { ok: true };
})()"""

_STOPPED_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const stop = document.querySelector('[data-testid="stop-thinking-button"]');
  const card = document.querySelector('[data-testid="reasoning-process-accordion"]');
  const labels = card
    ? Array.from(card.querySelectorAll('button')).map((b) => b.getAttribute('aria-label') || '')
    : [];
  return {
    ready: !stop && !(store?.loading || store?.isStreaming),
    hasCard: Boolean(card),
    labels,
    bodyLength: document.body.innerText.length,
  };
})()"""

_DONE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const stop = document.querySelector('[data-testid="stop-thinking-button"]');
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const assistants = msgs.filter((m) => m?.role === 'assistant');
  const last = assistants.length ? assistants[assistants.length - 1] : null;
  const reply = String(last?.content || '');
  const reasoning = String(last?.reasoning || '');
  const card = document.querySelector('[data-testid="reasoning-process-accordion"]');
  const labels = card
    ? Array.from(card.querySelectorAll('button')).map((b) => b.getAttribute('aria-label') || '')
    : [];
  return {
    ready: !stop && !(store?.loading || store?.isStreaming) && reply.trim().length > 0,
    replyLength: reply.trim().length,
    reasoningLength: reasoning.length,
    hasCard: Boolean(card),
    labels,
  };
})()"""


def _api(method: str, url: str, timeout: float = 30.0) -> tuple[int, str]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _chat_ids(api_url: str) -> set[str]:
    status, body = _api("GET", f"{api_url}/api/v1/chats?page=1&page_size=20")
    if status != 200:
        return set()
    items = (json.loads(body).get("data") or {}).get("items") or []
    return {str(item.get("id")) for item in items if item.get("id")}


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_reasoning_live_and_stop_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    before = _chat_ids(api_url)

    try:
        with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            ensure_desktop_viewport(client, page)

            saw_thinking = False
            thinking: dict[str, object] = {}
            last_done: dict[str, object] = {}

            for _attempt in range(3):
                sent = client.evaluate(page, _SEND_JS.replace("PROMPT", json.dumps(_PROMPT)), timeout_sec=60.0)
                assert isinstance(sent, dict) and sent.get("ok") is True, sent
                try:
                    thinking = wait_for_state(client, page, _THINKING_JS, timeout_sec=75.0)
                    saw_thinking = True
                    break
                except AssertionError:
                    last_done = wait_for_state(client, page, _DONE_JS, timeout_sec=180.0)
                    assert isinstance(last_done, dict) and last_done.get("ready") is True, last_done

            print(
                "E2E_LIVE_PATH",
                json.dumps({"sawThinking": saw_thinking, "replyLength": last_done.get("replyLength")}),
                flush=True,
            )

            if saw_thinking:
                stop = thinking.get("stop") or {}
                assert int(stop.get("height", 0)) >= 40, thinking
                assert "思考" in str(thinking.get("cardText") or ""), thinking
                stopped = client.evaluate(page, _STOP_JS, timeout_sec=30.0)
                assert isinstance(stopped, dict) and stopped.get("ok") is True, stopped
                done = wait_for_state(client, page, _STOPPED_JS, timeout_sec=120.0)
                assert isinstance(done, dict) and done.get("ready") is True, done
                assert done.get("hasCard") is True, done
                assert any("思考" in label for label in done.get("labels") or []), done
            else:
                assert int(last_done.get("replyLength", 0)) > 0, last_done

            # Whenever the turn produced a chain, the card must be mounted with localized controls.
            if int(done.get("reasoningLength", 0)) > 0 or saw_thinking:
                assert done.get("hasCard") is True, done
                assert any("思考" in label for label in done.get("labels") or []), done
    finally:
        for chat_id in _chat_ids(api_url) - before:
            _api("DELETE", f"{api_url}/api/v1/chats/{chat_id}", timeout=30.0)
