"""Chrome E2E: a reasoning chain folds once the answer settles, and the reader's choice then sticks.

Two nodes, one UI scenario each:

* history: a finished message opens collapsed; once the reader opens it, it stays open (it is the
  reader's block now) and a block the reader closed stays closed;
* live: a turn driven through the composer shows the chain open while the model thinks, folds it after
  the answer settled, and a chain the reader reopens is not folded again.

Model reasoning is non-deterministic, so the live node retries the turn when the model produced no
reasoning chain, and fails loudly (instead of passing vacuously) when no attempt produced one. The
"open while thinking" assertion applies only when a thinking phase (loading, no answer yet) was observed;
otherwise the run prints E2E_FOLD_THINKING_PHASE_NOT_SEEN.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    guarded_urlopen,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

if TYPE_CHECKING:
    from chrome_mcp.client import ChromeMcpClient, McpPage

_PROMPT = "请一步步推理：一个农夫有17只羊，除了9只以外都死了，还剩几只？先列出推理步骤，再给出结论，正文不少于 200 字。"
# The reader owns the block after one click; longer than the 1 s auto-fold delay plus render slack.
_HOLD_OPEN_MS = 3500
_HOLD_CLOSED_MS = 2500
_LIVE_ATTEMPTS = 2
# The auto-fold timer restarts on every content or reasoning change and fires 1 s later: the live observer
# waits for 2 s of silence plus 1.5 s of render slack before the fold is judged.
_STREAM_QUIET_MS = 3500

_ACCORDION_STATE_JS = """(() => {
  const acc = document.querySelector('[data-testid="reasoning-process-accordion"]');
  const toggles = acc ? Array.from(acc.querySelectorAll('button[aria-expanded]')) : [];
  const expanded = toggles.length > 0 && toggles.every((b) => b.getAttribute('aria-expanded') === 'true');
  return {
    ready: toggles.length > 0 && expanded === EXPECTED,
    present: Boolean(acc),
    expanded,
    bodyMounted: Boolean(acc && acc.querySelector('[id^="reasoning-body-"]')),
  };
})()"""

_CLICK_CHEVRON_JS = """(() => {
  const acc = document.querySelector('[data-testid="reasoning-process-accordion"]');
  const chevron = acc ? acc.querySelector('button[aria-expanded][aria-label]') : null;
  if (!chevron) return { ok: false, reason: 'chevron-missing' };
  chevron.click();
  return { ok: true, label: chevron.getAttribute('aria-label') };
})()"""

_HOLD_JS = """(async () => {
  const until = Date.now() + HOLD_MS;
  const samples = [];
  while (Date.now() < until) {
    const acc = document.querySelector('[data-testid="reasoning-process-accordion"]');
    const toggles = acc ? Array.from(acc.querySelectorAll('button[aria-expanded]')) : [];
    samples.push(toggles.length > 0 && toggles.every((b) => b.getAttribute('aria-expanded') === 'true'));
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return { samples };
})()"""

# Sends the prompt without awaiting the bridge's own completion heuristic, then samples the store and the
# card every 100 ms until the stream has been quiet (no content or reasoning change) for QUIET_MS. The
# fold timer restarts on every change and fires 1 s later, so a bursty stream cannot end the observation
# before the fold is due. Sampling in-page keeps the timeline free of CDP round-trip jitter; `transitions`
# records every loading/card/expanded change so a failure shows what the page was doing.
_SEND_AND_OBSERVE_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, reason: 'no-bridge' };
  if (bridge.setActionMode) bridge.setActionMode('agent');
  // Only the assistant row and card added by this send count: a retry must not observe the previous turn's.
  const assistantsOf = (state) => (Array.isArray(state?.messages) ? state.messages : []).filter((m) => m?.role === 'assistant');
  const cardsOf = () => Array.from(document.querySelectorAll('[data-testid="reasoning-process-accordion"]'));
  const baselineRows = assistantsOf(window.__myrmChatStore?.getState?.()).length;
  const baselineCards = cardsOf().length;
  void bridge.sendChatMessage(PROMPT).catch(() => undefined);

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const sample = () => {
    const state = window.__myrmChatStore?.getState?.();
    const rows = assistantsOf(state);
    const last = rows.length > baselineRows ? rows[rows.length - 1] : null;
    const cards = cardsOf();
    const acc = cards.length > baselineCards ? cards[cards.length - 1] : null;
    const toggles = acc ? Array.from(acc.querySelectorAll('button[aria-expanded]')) : [];
    return {
      loading: Boolean(state?.loading || state?.isStreaming),
      content: String(last?.content || ''),
      reasoningLength: String(last?.reasoning || '').length,
      hasCard: Boolean(acc),
      expanded: toggles.length > 0 && toggles.every((b) => b.getAttribute('aria-expanded') === 'true'),
    };
  };

  const startedAt = performance.now();
  const at = () => Math.round(performance.now() - startedAt);
  const timeline = {
    thinkingPhaseSeen: false,
    thinkingExpandedSeen: false,
    firstContentMs: null,
    lastContentChangeMs: null,
    lastReasoningChangeMs: null,
    settledMs: null,
    firstFoldedAfterContentMs: null,
  };
  const transitions = [];
  let previousShape = '';
  let lastLength = 0;
  let lastReasoningLength = 0;
  let lastChangeMs = 0;
  let final = sample();
  while (at() < DEADLINE_MS) {
    final = sample();
    const trimmed = final.content.trim();
    if (final.loading && !trimmed && final.hasCard) {
      timeline.thinkingPhaseSeen = true;
      if (final.expanded) timeline.thinkingExpandedSeen = true;
    }
    if (trimmed && timeline.firstContentMs === null) timeline.firstContentMs = at();
    if (final.content.length !== lastLength) {
      lastLength = final.content.length;
      lastChangeMs = timeline.lastContentChangeMs = at();
    }
    if (final.reasoningLength !== lastReasoningLength) {
      lastReasoningLength = final.reasoningLength;
      lastChangeMs = timeline.lastReasoningChangeMs = at();
    }
    if (trimmed && !final.loading && timeline.settledMs === null) timeline.settledMs = at();
    if (trimmed && final.hasCard && !final.expanded && timeline.firstFoldedAfterContentMs === null) {
      timeline.firstFoldedAfterContentMs = at();
    }
    const shape = `${final.loading}|${final.hasCard}|${final.expanded}`;
    if (shape !== previousShape) {
      previousShape = shape;
      transitions.push({
        atMs: at(),
        loading: final.loading,
        hasCard: final.hasCard,
        expanded: final.expanded,
        contentLength: final.content.length,
        reasoningLength: final.reasoningLength,
      });
    }
    if (trimmed && at() - lastChangeMs >= QUIET_MS) break;
    await sleep(100);
  }
  return {
    ok: true,
    timeline,
    transitions,
    endedAtMs: at(),
    reasoningLength: final.reasoningLength,
    contentLength: final.content.trim().length,
    hasCard: final.hasCard,
    finalExpanded: final.expanded,
  };
})()"""


def _api(method: str, url: str, payload: dict[str, object] | None = None, timeout: float = 30.0) -> tuple[int, str]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data else {},
        method=method,
    )
    try:
        with guarded_urlopen(request, timeout_sec=timeout) as response:
            return response.status, response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", "replace")


def _chat_ids(api_url: str) -> set[str]:
    status, body = _api("GET", f"{api_url}/api/v1/chats?page=1&page_size=20")
    if status != 200:
        return set()
    items = (json.loads(body).get("data") or {}).get("items") or []
    return {str(item.get("id")) for item in items if item.get("id")}


def _seed_reasoning_turn(api_url: str, chat_id: str) -> None:
    """Run one real turn until the model persists a reasoning chain."""
    status, body = _api(
        "POST",
        f"{api_url}/api/v1/agents/agent-stream",
        {
            "messageId": f"e2e-fold-{int(time.time() * 1000)}",
            "query": _PROMPT,
            "action_mode": "agent",
            "chat_id": chat_id,
            "reasoning_display_mode": "collapsed",
        },
        timeout=240.0,
    )
    assert status == 200, body[:400]
    status, messages = _api("GET", f"{api_url}/api/v1/chats/{chat_id}/messages?page=1&page_size=20", timeout=60.0)
    assert status == 200, messages[:400]
    items = (json.loads(messages).get("data") or {}).get("messages") or []
    assistants = [item for item in items if item.get("role") == "assistant"]
    assert assistants, messages[:400]
    metadata = assistants[-1].get("metadata") or {}
    assert metadata.get("reasoning_content") or metadata.get("reasoning"), f"no reasoning persisted: {metadata}"


def _state(client: ChromeMcpClient, page: McpPage, *, expanded: bool, timeout_sec: float = 60.0) -> dict[str, object]:
    return wait_for_state(
        client,
        page,
        _ACCORDION_STATE_JS.replace("EXPECTED", json.dumps(expanded)),
        timeout_sec=timeout_sec,
    )


def _click_chevron(client: ChromeMcpClient, page: McpPage) -> None:
    clicked = client.evaluate(page, _CLICK_CHEVRON_JS, timeout_sec=30.0)
    assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked


def _hold(client: ChromeMcpClient, page: McpPage, hold_ms: int) -> list[bool]:
    held = client.evaluate(page, _HOLD_JS.replace("HOLD_MS", str(hold_ms)), timeout_sec=hold_ms / 1000 + 30.0)
    assert isinstance(held, dict), held
    samples = held.get("samples")
    assert isinstance(samples, list) and samples, held
    return [bool(sample) for sample in samples]


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(420)
def test_reasoning_history_open_stays_open_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    chat_id = f"e2e-reasoning-fold-history-{int(time.time())}"
    _seed_reasoning_turn(api_url, chat_id)
    try:
        with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            ensure_desktop_viewport(client, page)

            closed = _state(client, page, expanded=False)
            assert closed.get("bodyMounted") is False, closed

            _click_chevron(client, page)
            opened = _state(client, page, expanded=True)
            assert opened.get("bodyMounted") is True, opened
            open_samples = _hold(client, page, _HOLD_OPEN_MS)
            print("E2E_FOLD_HISTORY_OPEN", json.dumps({"samples": len(open_samples), "allOpen": all(open_samples)}), flush=True)
            assert all(open_samples), f"reader-opened chain folded by itself: {open_samples}"

            _click_chevron(client, page)
            _state(client, page, expanded=False)
            closed_samples = _hold(client, page, _HOLD_CLOSED_MS)
            assert not any(closed_samples), f"reader-closed chain reopened by itself: {closed_samples}"
    finally:
        _api("DELETE", f"{api_url}/api/v1/chats/{chat_id}", timeout=30.0)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_reasoning_live_folds_after_answer_chrome_e2e() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    before = _chat_ids(api_url)

    try:
        with open_mcp_page(ui_url, timeout_ms=120_000) as (client, page):
            dismiss_blocking_modals(client, page)
            ensure_desktop_viewport(client, page)

            observed: dict[str, object] = {}
            for _attempt in range(_LIVE_ATTEMPTS):
                script = (
                    _SEND_AND_OBSERVE_JS.replace("PROMPT", json.dumps(_PROMPT))
                    .replace("DEADLINE_MS", "150000")
                    .replace("QUIET_MS", str(_STREAM_QUIET_MS))
                )
                raw = client.evaluate(page, script, timeout_sec=200.0)
                assert isinstance(raw, dict) and raw.get("ok") is True, raw
                observed = raw
                if int(observed.get("reasoningLength") or 0) > 0 and int(observed.get("contentLength") or 0) > 0:
                    break
            print("E2E_FOLD_LIVE_TIMELINE", json.dumps(observed, ensure_ascii=False), flush=True)

            assert int(observed.get("contentLength") or 0) > 0, f"the turn produced no answer: {observed}"
            assert int(observed.get("reasoningLength") or 0) > 0, (
                f"no attempt produced a reasoning chain, the fold cannot be verified: {observed}"
            )
            timeline = observed.get("timeline")
            assert isinstance(timeline, dict), observed
            if timeline.get("thinkingPhaseSeen"):
                assert timeline.get("thinkingExpandedSeen") is True, f"chain was folded while thinking: {observed}"
            else:
                print(
                    "E2E_FOLD_THINKING_PHASE_NOT_SEEN",
                    "no visible thinking phase was streamed, so 'open while thinking' was not asserted",
                    flush=True,
                )
            assert timeline.get("firstFoldedAfterContentMs") is not None, f"chain never folded after the answer: {observed}"
            assert observed.get("finalExpanded") is False, f"chain is still open after the answer settled: {observed}"

            _click_chevron(client, page)
            _state(client, page, expanded=True)
            reopened = _hold(client, page, _HOLD_OPEN_MS)
            assert all(reopened), f"reader-reopened chain folded again: {reopened}"
    finally:
        for chat_id in _chat_ids(api_url) - before:
            _api("DELETE", f"{api_url}/api/v1/chats/{chat_id}", timeout=30.0)
