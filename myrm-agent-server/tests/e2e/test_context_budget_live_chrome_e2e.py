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

_SEND_READY_JS = """(() => {
  const btn = document.querySelector('.message-send-btn');
  const bridge = window.__MYRM_E2E_CHAT__;
  return {
    ready: Boolean(bridge?.sendChatMessage) && Boolean(bridge?.attachToChat),
    hasBtn: Boolean(btn),
    disabled: btn?.disabled ?? null,
    hasBridgeSend: Boolean(bridge?.sendChatMessage),
  };
})()"""

_SEND_VIA_BRIDGE_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-sendChatMessage' };
  // agent mode avoids the fast/deep_research search-configuration guard.
  if (bridge?.setActionMode) bridge.setActionMode('agent');
  return await bridge.sendChatMessage(PROMPT);
})()"""

_AWAIT_LIVE_REPLY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages ?? [];
  const assistants = msgs.filter(
    (m) => (m.role === 'assistant' || m.type === 'assistant') && Boolean(m.contextBudget)
  );
  const last = assistants.length ? assistants[assistants.length - 1] : null;
  const streaming = Boolean(store?.isStreaming || store?.loading);
  return {
    // Ready only once the live turn has produced an ADDITIONAL budgeted assistant.
    ready: assistants.length >= MIN_BUDGET && !streaming,
    budgetedCount: assistants.length,
    streaming,
    liveTurnCount: last?.contextBudget?.turn_count ?? null,
    liveMessagesEstimated: Number(last?.contextBudget?.messages_estimated_tokens ?? 0),
    liveBoundTools: Number(last?.contextBudget?.bound_tools_overhead_tokens ?? 0),
    liveCurrentTokens: Number(last?.contextBudget?.current_tokens ?? 0),
    liveHealth: last?.contextBudget?.health_status ?? null,
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
    ready: ok,
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

        baseline = client.evaluate(
            page, _AWAIT_LIVE_REPLY_JS.replace("MIN_BUDGET", "0"), timeout_sec=15.0
        )
        assert isinstance(baseline, dict), baseline
        baseline_budgeted = int(baseline.get("budgetedCount") or 0)
        assert baseline_budgeted >= 1, f"retention fixture should carry a seeded budget: {baseline}"
        # The seeded fixture metadata has no turn_count at all — only a real runtime
        # snapshot produces it. That makes its appearance after the turn the proof.
        assert baseline.get("liveTurnCount") is None, (
            f"seeded fixture must not fabricate turn_count: {baseline}"
        )

        send_ready = wait_for_state(client, page, _SEND_READY_JS, timeout_sec=60.0)
        assert isinstance(send_ready, dict) and send_ready.get("ready") is True, send_ready

        sent = client.evaluate(
            page,
            _SEND_VIA_BRIDGE_JS.replace("PROMPT", json.dumps(_LIVE_PROMPT)),
            timeout_sec=200.0,
        )
        assert isinstance(sent, dict) and sent.get("ok") is True, sent

        reply = wait_for_state(
            client,
            page,
            _AWAIT_LIVE_REPLY_JS.replace("MIN_BUDGET", str(baseline_budgeted + 1)),
            timeout_sec=180.0,
        )
        assert isinstance(reply, dict) and reply.get("ready") is True, reply

        # A live turn must add a budget whose turn_count is a real server value.
        assert reply.get("budgetedCount", 0) > baseline_budgeted, (
            f"live turn produced no new contextBudget: baseline={baseline} reply={reply}"
        )
        live_turns = reply.get("liveTurnCount")
        assert isinstance(live_turns, int), (
            f"live turn_count missing — runtime never emitted it: {reply}"
        )
        assert live_turns >= 1, reply
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
