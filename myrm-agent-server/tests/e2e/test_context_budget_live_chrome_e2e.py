"""Real Chrome MCP E2E: context budget breakdown after a real agent turn.

Sends a live message through the WebUI composer, waits for the real model reply, then
verifies the context usage panel surfaces a live ``contextBudget`` — including a
server-authoritative ``turn_count``.

Why this exists: the seeded context-retention E2E reads fixture metadata, so it cannot
observe what the runtime computes. ``turn_count`` is produced by the checkpoint read path
and only reaches the payload when the thread's checkpoint is readable, so a live turn is
the only way to confirm the server value actually lands in the UI.

Bypasses nothing: real Chrome (:9333), real WebUI (:3000), real backend (:8080), real LLM.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_LIVE_PROMPT = "Reply with exactly one word: hello."

_TYPE_MESSAGE_JS = """(() => {
  const el = document.querySelector('[data-chat-input]');
  if (!el) return { ok: false, err: 'input-not-found' };
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return { ok: false, err: 'setter-not-found' };
  setter.call(el, PROMPT);
  el.setSelectionRange(el.value.length, el.value.length);
  el.dispatchEvent(new Event('input', { bubbles: true }));
  el.dispatchEvent(new Event('change', { bubbles: true }));
  return { ok: true, value: el.value };
})()"""

_SEND_READY_JS = """(() => {
  const btn = document.querySelector('.message-send-btn');
  const input = document.querySelector('[data-chat-input]');
  const store = window.__myrmChatStore?.getState?.();
  return {
    ready: Boolean(btn) && !btn.disabled && btn.getAttribute('aria-disabled') !== 'true',
    hasBtn: Boolean(btn),
    disabled: btn?.disabled ?? null,
    inputValue: input?.value ?? null,
    isLoading: Boolean(store?.loading || store?.isStreaming),
  };
})()"""

_CLICK_SEND_JS = """(() => {
  const btn = document.querySelector('.message-send-btn');
  if (!btn || btn.disabled) return { ok: false, err: 'send-disabled' };
  btn.click();
  return { ok: true };
})()"""

_ASSISTANT_REPLY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages ?? [];
  const assistants = msgs.filter((m) => m.role === 'assistant' || m.type === 'assistant');
  const assistant = assistants.find((m) => String(m.content || m.text || '').trim().length > 0);
  const budgeted = assistants.filter((m) => Boolean(m.contextBudget));
  const lastBudgeted = budgeted.length ? budgeted[budgeted.length - 1] : null;
  return {
    ready: Boolean(assistant) && !Boolean(store?.isStreaming || store?.loading),
    hasAssistant: Boolean(assistant),
    sample: String(assistant?.content || assistant?.text || '').slice(0, 60),
    // Baseline: a seeded chat must have NO contextBudget before the live turn.
    budgetedCount: budgeted.length,
    liveTurnCount: lastBudgeted?.contextBudget?.turn_count ?? null,
    liveMessagesEstimated: Number(lastBudgeted?.contextBudget?.messages_estimated_tokens ?? 0),
    liveBoundTools: Number(lastBudgeted?.contextBudget?.bound_tools_overhead_tokens ?? 0),
    liveCurrentTokens: Number(lastBudgeted?.contextBudget?.current_tokens ?? 0),
    liveHealth: lastBudgeted?.contextBudget?.health_status ?? null,
  };
})()"""

_LIVE_BUDGET_JS = """(() => {
  const indicator = document.querySelector('[data-testid="context-usage-indicator"]');
  if (indicator) indicator.click();
  const panel = document.querySelector('[data-testid="context-budget-breakdown"]');
  const store = window.__myrmChatStore?.getState?.();
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  const budgeted = msgs.filter(
    (m) => (m?.role === 'assistant' || m?.type === 'assistant') && Boolean(m?.contextBudget)
  );
  const budget = budgeted.length ? budgeted[budgeted.length - 1].contextBudget : null;
  return {
    hasPanel: Boolean(panel),
    budgetedCount: budgeted.length,
    turnCount: budget?.turn_count ?? null,
    turnCountIsNumber: typeof budget?.turn_count === 'number',
    messagesEstimated: Number(budget?.messages_estimated_tokens ?? 0),
    boundTools: Number(budget?.bound_tools_overhead_tokens ?? 0),
    currentTokens: Number(budget?.current_tokens ?? 0),
    healthStatus: budget?.health_status ?? null,
  };
})()"""

_CLOSE_PANEL_JS = """(() => {
  const indicator = document.querySelector('[data-testid="context-usage-indicator"]');
  if (indicator) indicator.click();
  return { ok: true };
})()"""

_ATTACH_CHAT_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) return { ok: false, err: 'no-bridge' };
  const input = document.querySelector('[data-chat-input]');
  const store = window.__myrmChatStore?.getState?.();
  const ok =
    Boolean(input)
    && Boolean(store?.isMessagesLoaded)
    && !Boolean(store?.notFound)
    && !Boolean(store?.loadError);
  return {
    ok,
    hasInput: Boolean(input),
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
    notFound: Boolean(store?.notFound),
    loadError: Boolean(store?.loadError),
  };
})()"""


def _seed_empty_chat(ui_url: str) -> dict[str, object]:
    """Seed the retention chat: proven to render the composer and usage indicator.

    Seeded through the **UI origin** rather than ``get_e2e_api_url()``: the API helper can
    resolve to an isolated backend while the WebUI proxies to the shared one, which makes
    a chat created via the API invisible to the UI (``notFound``). Going through the UI's
    own proxy guarantees the chat lands in the backend the browser actually talks to.

    That fixture carries one seeded assistant turn, so the live turn is verified by
    difference (budget count and turn_count must both grow) rather than by presence.
    """
    seeded = http_json(
        "POST",
        f"{ui_url.rstrip('/')}/api/v1/chats/test/seed-context-retention-fixture",
    )
    assert isinstance(seeded, dict), seeded
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2econtextret"), seeded
    return seeded


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_live_turn_emits_context_budget_with_server_turn_count() -> None:
    """One real agent turn must surface a live context_budget carrying turn_count.

    Baseline discipline: the seeded chat starts with zero messages, so any contextBudget
    observed after the turn is produced by the live turn — not by fixture metadata.
    """
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_empty_chat(ui_url)
    chat_id = str(seeded["chat_id"])
    agent_id = str(seeded["agent_id"])
    chat_path = str(seeded.get("ui_path") or f"/{chat_id}?agentId={agent_id}")
    chat_url = f"{ui_url.rstrip('/')}{chat_path}"
    home_url = f"{ui_url.rstrip('/')}/"
    warm_ui_route("/")
    warm_ui_route(chat_path)

    with open_mcp_page(home_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        # Hydrate the Turbopack client on the shell route first; a cold chat route
        # cannot finish hydration within the bridge timeout under parallel load.
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=home_url)
        assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)

        client.navigate(page, chat_url)  # type: ignore[attr-defined]
        time.sleep(1.5)
        dismiss_blocking_modals(client, page)

        attached = wait_for_state(client, page, _ATTACH_CHAT_JS, timeout_sec=90.0)
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        baseline = client.evaluate(page, _ASSISTANT_REPLY_JS, timeout_sec=15.0)
        assert isinstance(baseline, dict), baseline
        baseline_budgeted = int(baseline.get("budgetedCount") or 0)
        baseline_turns = baseline.get("liveTurnCount")
        assert baseline_budgeted >= 1, f"retention fixture should carry a seeded budget: {baseline}"
        assert isinstance(baseline_turns, int), baseline

        typed = client.evaluate(
            page,
            _TYPE_MESSAGE_JS.replace("PROMPT", json.dumps(_LIVE_PROMPT)),
            timeout_sec=15.0,
        )
        assert isinstance(typed, dict) and typed.get("ok") is True, typed

        send_ready = wait_for_state(client, page, _SEND_READY_JS, timeout_sec=45.0)
        assert isinstance(send_ready, dict) and send_ready.get("ready") is True, send_ready

        clicked = client.evaluate(page, _CLICK_SEND_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked

        reply = wait_for_state(client, page, _ASSISTANT_REPLY_JS, timeout_sec=180.0)
        assert isinstance(reply, dict) and reply.get("ready") is True, reply
        assert str(reply.get("sample") or "").strip(), reply

        # A live turn must add a budget whose turn_count advances by exactly one.
        assert reply.get("budgetedCount", 0) > baseline_budgeted, (
            f"live turn produced no new contextBudget: baseline={baseline} reply={reply}"
        )
        assert isinstance(reply.get("liveTurnCount"), int), (
            f"live turn_count missing from contextBudget: {reply}"
        )
        assert reply["liveTurnCount"] == baseline_turns + 1, (baseline, reply)
        assert reply["liveMessagesEstimated"] > 0, reply
        assert reply["liveCurrentTokens"] > 0, reply
        assert reply["liveHealth"] in {"healthy", "warning", "critical"}, reply

        panel = wait_for_state(client, page, _LIVE_BUDGET_JS, timeout_sec=60.0)
        assert isinstance(panel, dict), panel
        assert panel.get("turnCountIsNumber") is True, panel
        assert panel["turnCount"] == reply["liveTurnCount"], (panel, reply)
        assert panel["messagesEstimated"] > 0, panel

        client.evaluate(page, _CLOSE_PANEL_JS, timeout_sec=15.0)
        time.sleep(0.2)
