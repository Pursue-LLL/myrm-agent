"""Fast-search turns sent through the E2E chat bridge, each proven to have run in fast mode.

The harness's own ``send_message`` switches the chat to agent mode before it sends, so a test that has to
exercise ``action_mode: fast`` sends through the bridge with the action mode preserved. ``run_fast_search_turn``
proves the mode three ways: the chat is in fast mode before the send and after the turn, and every agent-stream
request the page issued carried ``action_mode: fast``. The request body is what the backend runs a turn by; the
page's own mode and the lane an event names are not evidence of it.

A turn has ended once its assistant message carries the completion status the terminal event writes. The page's
``loading`` flag cannot mark the end: the stream watchdog can clear it while the answer is still streaming.
"""

from __future__ import annotations

import asyncio
import json
from typing import Protocol

from tests.support.e2e_runtime_guard import heartbeat_once

_POLL_INTERVAL_SEC = 2.0
_PROMPT_PLACEHOLDER = "__PROMPT__"


class PageEvaluator(Protocol):
    """The page-script entry of a chat session (``McpChatSession.evaluate``)."""

    async def evaluate(self, expression: str, *, await_promise: bool = True) -> object: ...


# Sends without waiting for the bridge's kickoff verdict: the bridge gives up on a send that shows no UI
# progress within 12 s, which only reports the send; the turn itself is not cancelled. The verdict is kept in
# `lastSubmitResult`, which `_PAGE_PROBE_JS` reports.
_SEND_TURN_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, reason: 'no-bridge' };
  void bridge.sendChatMessage(__PROMPT__, { preserveActionMode: true }).catch(() => undefined);
  return { ok: true };
})()"""

# The action mode of every agent-stream request, in send order. The first call installs the recorder, later
# calls read it.
_WIRE_MODES_JS = """(() => {
  if (!window.__fastTurnWireModes) {
    const modes = [];
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : (input?.url ?? '');
      if (url.includes('/agents/agent-stream') && typeof init?.body === 'string') {
        try {
          modes.push(JSON.parse(init.body).action_mode ?? null);
        } catch {
          modes.push('unparsable');
        }
      }
      return nativeFetch(input, init);
    };
    window.__fastTurnWireModes = modes;
  }
  return window.__fastTurnWireModes;
})()"""

# What the page reports about the chat right now, including how the bridge's last send ended; a failed turn is
# described with it so a stalled send reads differently from a mode flip.
_PAGE_PROBE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const store = window.__myrmChatStore?.getState?.();
  const submit = bridge?.lastSubmitResult;
  return {
    chatId: store?.chatId ?? null,
    actionMode: bridge?.getActionMode?.() ?? null,
    sendReady: bridge?.isSendReady?.() ?? null,
    loading: Boolean(store?.loading),
    messageCount: Array.isArray(store?.messages) ? store.messages.length : null,
    lastSubmit: submit ? { ok: submit.ok ?? null, err: submit.err ?? null, mode: submit.mode ?? null } : null,
  };
})()"""

# How many assistant messages the chat has and whether the newest one has seen its terminal event.
_TURN_STATE_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const assistants = (store?.messages ?? []).filter((m) => m?.role === 'assistant');
  return {
    assistants: assistants.length,
    completed: Boolean(assistants[assistants.length - 1]?.completionStatus),
    loading: Boolean(store?.loading),
  };
})()"""


async def _read_object(chat: PageEvaluator, script: str) -> dict[str, object]:
    raw = await chat.evaluate(script, await_promise=False)
    return raw if isinstance(raw, dict) else {"raw": raw}


async def _probe_page(chat: PageEvaluator) -> dict[str, object]:
    """Action mode and send readiness as the page reports them.

    A page that cannot answer is reported instead of raised: this runs while a failure is being described,
    and the probe must not replace the failure it describes.
    """
    try:
        return await _read_object(chat, _PAGE_PROBE_JS)
    except Exception as exc:
        return {"probeError": f"{type(exc).__name__}: {exc}"[:200]}


async def _wait_turn_completed(chat: PageEvaluator, *, assistants: int, timeout_sec: float) -> None:
    """Wait until the chat has ``assistants`` assistant messages and the newest one has completed."""
    clock = asyncio.get_running_loop().time
    deadline = clock() + timeout_sec
    last: dict[str, object] = {}
    while clock() < deadline:
        heartbeat_once()
        last = await _read_object(chat, _TURN_STATE_JS)
        if last.get("assistants") == assistants and last.get("completed") is True:
            return
        await asyncio.sleep(_POLL_INTERVAL_SEC)
    raise TimeoutError(f"turn {assistants} did not complete within {timeout_sec:.0f}s: {last} page: {await _probe_page(chat)}")


async def run_fast_search_turn(chat: PageEvaluator, prompt: str, *, turn: int, timeout_sec: float) -> dict[str, object]:
    """Send ``prompt`` as turn ``turn`` of the chat, wait for it to end and prove it ran in fast mode.

    ``turn`` counts from 1 and must be the position of this turn in both the chat and this helper's request
    recorder, so every turn of the chat has to be sent through here. Returns the page state after the turn.
    """
    before = await _probe_page(chat)
    assert before.get("actionMode") == "fast", f"turn {turn}: the chat was not in fast mode when the send started: {before}"
    await chat.evaluate(_WIRE_MODES_JS, await_promise=False)
    sent = await chat.evaluate(_SEND_TURN_JS.replace(_PROMPT_PLACEHOLDER, json.dumps(prompt)), await_promise=False)
    assert isinstance(sent, dict) and sent.get("ok") is True, f"turn {turn}: the send was not issued: {sent}"
    await _wait_turn_completed(chat, assistants=turn, timeout_sec=timeout_sec)
    after = await _probe_page(chat)
    wire = await chat.evaluate(_WIRE_MODES_JS, await_promise=False)
    print(
        f"E2E_FAST_TURN{turn}: mode before={before.get('actionMode')} after={after.get('actionMode')} "
        f"wire={wire} send={after.get('lastSubmit')}",
        flush=True,
    )
    assert after.get("actionMode") == "fast", f"turn {turn}: the chat left fast mode during the turn: {after}"
    assert isinstance(wire, list) and len(wire) >= turn and set(wire) == {"fast"}, (
        f"turn {turn}: the request did not go out in fast mode: wire={wire} page={after}"
    )
    return after
