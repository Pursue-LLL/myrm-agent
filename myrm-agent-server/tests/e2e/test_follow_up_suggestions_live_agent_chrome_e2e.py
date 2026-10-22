"""Chrome LIVE E2E: a finished answer offers follow-up questions, and a click on one asks it.

Nothing is seeded but the agent. The user types a question in the composer, the live model answers, the lite
model files related questions under the answer (a second live model call that starts when the turn ends), and a
click on one of them sends it as the next question.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_follow_up_suggestions_live_agent_chrome_e2e.py
"""

from __future__ import annotations

import contextlib
import json
import sys
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    backend_log_path,
    dump_backend_log_on_failure,
    snapshot_backend_log_offset,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    prepare_e2e_ui_session,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_composer import describe_page, drive_chat_turn  # noqa: E402
from tests.support.chrome_skill_hooks_live_e2e import SkillChat  # noqa: E402
from tests.support.chrome_skill_hooks_observe import (  # noqa: E402
    completed_assistant_replies,
    stored_messages,
    wait_user_message_persisted,
)
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger  # noqa: E402

_QUESTION = "Why is the sky blue? Answer in one short sentence."
_AGENT_SYSTEM_PROMPT = "You answer every question in one short sentence and follow the user's formatting request."

# The agent's own configuration reaches the page asynchronously after the chat opens; a message sent before that
# runs on the default agent.
_AGENT_BOUND_JS = """((agentId) => {
  const bound = window.__myrmChatStore?.getState?.()?.agentConfig?.agentId ?? null;
  return { ready: bound === agentId, bound };
})"""

# Chips are rendered under the last answer only while the chat is idle.
_CHIPS_JS = """(() => {
  const texts = Array.from(document.querySelectorAll('[data-testid="message-suggestion"]'))
    .map((chip) => (chip.textContent || '').trim());
  return { ready: texts.length > 0, texts };
})()"""

_CLICK_CHIP_JS = """(() => {
  const chip = document.querySelector('[data-testid="message-suggestion"]');
  if (!chip) return { ok: false, err: 'missing-chip' };
  const text = (chip.textContent || '').trim();
  chip.click();
  return { ok: true, text };
})()"""

# Everything that can make the page start its mount-time fetches again, with timestamps: reconnects of the push
# channel, resync events, tab visibility/focus changes, history navigations, a composer that was re-created and
# the chat-store fields that change (a store update re-renders the chat window).
_PAGE_PULSE_JS = """(() => {
  if (window.__MYRM_PAGE_PULSE__) return { ok: true };
  const now = () => Math.round(performance.now());
  const pulse = (window.__MYRM_PAGE_PULSE__ = {
    pushChannels: [], resync: [], visibility: [], focus: 0, navigations: [], composerNodes: 0, errors: [],
    storeUpdates: 0, storeKeys: {},
  });
  window.__myrmChatStore?.subscribe?.((state, previous) => {
    pulse.storeUpdates += 1;
    for (const key of Object.keys(state)) {
      if (state[key] !== previous[key]) pulse.storeKeys[key] = (pulse.storeKeys[key] ?? 0) + 1;
    }
  });
  const NativeEventSource = window.EventSource;
  window.EventSource = function (url, init) {
    const source = new NativeEventSource(url, init);
    const entry = { url: String(url).slice(-60), created: now(), opened: [], errors: [] };
    pulse.pushChannels.push(entry);
    source.addEventListener('open', () => entry.opened.push(now()));
    source.addEventListener('error', () => entry.errors.push(now()));
    return source;
  };
  window.EventSource.prototype = NativeEventSource.prototype;
  Object.setPrototypeOf(window.EventSource, NativeEventSource);
  window.addEventListener('app_resync_required', () => pulse.resync.push(now()));
  document.addEventListener('visibilitychange', () => pulse.visibility.push([now(), document.visibilityState]));
  window.addEventListener('focus', () => { pulse.focus += 1; });
  for (const name of ['pushState', 'replaceState']) {
    const native = history[name];
    history[name] = function (...args) {
      pulse.navigations.push([now(), name, String(args[2] ?? '').slice(-60)]);
      return native.apply(this, args);
    };
  }
  let lastInput = null;
  new MutationObserver(() => {
    const input = document.querySelector('[data-chat-input]');
    if (input && input !== lastInput) {
      lastInput = input;
      pulse.composerNodes += 1;
    }
  }).observe(document.body, { childList: true, subtree: true });
  window.addEventListener('error', (event) => pulse.errors.push(String(event.message).slice(0, 120)));
  window.addEventListener('unhandledrejection', (event) => pulse.errors.push(`rejection: ${String(event.reason).slice(0, 120)}`));
  return { ok: true };
})()"""

# What the page holds about the follow-ups of the answer that just ended, for a run where no chip appears.
_FOLLOW_UP_STATE_JS = """(() => {
  const state = window.__myrmChatStore?.getState?.();
  const assistants = (state?.messages ?? []).filter((message) => message.role === 'assistant');
  const last = assistants[assistants.length - 1];
  const trace = window.__MYRM_SEND_TRACE__ ?? [];
  // Every request since the send, grouped per endpoint: a storm of one call, or calls that never came back, is
  // what keeps the follow-up request from being answered.
  const endpoints = {};
  for (const entry of trace) {
    if (!entry.url) continue;
    const path = String(entry.url).replace(/^https?:\\/\\/[^/]+/, '').replace(/^\\/api\\/v1/, '').split('?')[0];
    const key = `${entry.method} ${path.replace(/e2efollowup[0-9a-f]+/g, ':chat').slice(0, 70)}`;
    const row = (endpoints[key] ??= { calls: 0, maxMs: 0, failed: 0, unanswered: 0 });
    row.calls += 1;
    row.maxMs = Math.max(row.maxMs, entry.ms ?? 0);
    if (entry.error) row.failed += 1;
    else if (entry.status === undefined) row.unanswered += 1;
  }
  const busiest = Object.entries(endpoints).sort((a, b) => b[1].calls - a[1].calls).slice(0, 14);
  return {
    loading: state?.loading ?? null,
    lastAnswerLength: (last?.content ?? '').length,
    storedSuggestions: last?.suggestions ?? [],
    suggestionRequests: trace.filter((entry) => String(entry.url ?? '').includes('/agents/suggestions')),
    requestsByEndpoint: Object.fromEntries(busiest),
    fetchBurstsAt: trace.filter((entry) => String(entry.url ?? '').includes('/agents/templates')).map((entry) => Math.round(entry.at / 1000)),
    lastMessageFields: last ? Object.fromEntries(Object.entries(last)
      .filter(([key]) => !['content', 'sources', 'steps'].includes(key))
      .map(([key, value]) => [key, typeof value === 'string' ? value.slice(0, 160)
        : value !== null && typeof value === 'object' ? `[${Array.isArray(value) ? 'array' : 'object'}:${Object.keys(value).length}]`
        : value])) : null,
    pulse: window.__MYRM_PAGE_PULSE__ ? {
      ...window.__MYRM_PAGE_PULSE__,
      pushChannels: window.__MYRM_PAGE_PULSE__.pushChannels.slice(-8),
      resync: window.__MYRM_PAGE_PULSE__.resync.slice(-12),
      navigations: window.__MYRM_PAGE_PULSE__.navigations.slice(-8),
      errors: window.__MYRM_PAGE_PULSE__.errors.slice(-6),
      storeKeys: Object.fromEntries(Object.entries(window.__MYRM_PAGE_PULSE__.storeKeys).sort((a, b) => b[1] - a[1]).slice(0, 10)),
    } : null,
    consoleErrors: trace.filter((entry) => entry.console).slice(-6),
  };
})()"""

_ANSWER_STATE_JS = """(() => {
  const state = window.__myrmChatStore?.getState?.();
  const assistants = (state?.messages ?? []).filter((message) => message.role === 'assistant');
  const last = assistants[assistants.length - 1];
  return { loading: state?.loading ?? null, shown: assistants.length, lastLength: (last?.content ?? '').length };
})()"""


def _call(js_function: str, argument: object) -> str:
    return f"({js_function})({json.dumps(argument)})"


@contextlib.contextmanager
def _backend_errors_on_failure(api_url: str) -> Iterator[None]:
    """Print the ERROR-level backend log lines written during the block when it raises.

    The log tail that ``dump_backend_log_on_failure`` prints is filled by background chatter during a long wait,
    while the error that ended the turn was written at its start.
    """
    start = snapshot_backend_log_offset(api_url)
    try:
        yield
    except BaseException:
        path = backend_log_path(api_url)
        if path.is_file():
            with path.open("rb") as handle:
                handle.seek(start)
                text = handle.read().decode("utf-8", errors="replace")
            hits = [line[:400] for line in text.splitlines() if " - ERROR - " in line or "Traceback" in line]
            print(f"BACKEND_ERRORS_ON_FAILURE ({len(hits)} lines):\n" + "\n".join(hits[:30]), flush=True)
        raise


def _create_agent(api_url: str, suffix: str) -> str:
    """Custom agent without tools: the turn is one model answer, so the follow-up call is the only other work."""
    created = http_json(
        "POST",
        f"{api_url}/api/v1/user-agents",
        body={
            "name": f"Follow-up Live E2E {suffix}",
            "description": "Live E2E agent that answers in one sentence",
            "system_prompt": _AGENT_SYSTEM_PROMPT,
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": [],
        },
    )
    assert isinstance(created, dict), created
    data = created.get("data")
    agent_id = data.get("id") if isinstance(data, dict) else created.get("id")
    assert isinstance(agent_id, str) and agent_id, created
    return agent_id


def _create_chat(api_url: str, chat_id: str, agent_id: str) -> None:
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Follow-up live E2E",
            "agent_id": agent_id,
            "action_mode": "agent",
            "messages": [],
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created


def _follow_up_report(client: ChromeMcpClient, page: McpPage) -> str:
    state = client.evaluate(page, _FOLLOW_UP_STATE_JS, timeout_sec=15.0)
    return f"follow-up state in the page: {json.dumps(state, ensure_ascii=False)}\n{describe_page(client, page)}"


def _wait_for_answer(
    client: ChromeMcpClient,
    page: McpPage,
    chat_id: str,
    api_url: str,
    *,
    count: int,
    page_settled: bool,
    timeout_sec: float,
) -> str:
    """The ``count``-th answer, once the server stored it as complete (and, with ``page_settled``, the page shows it).

    The page's loading flag alone does not say an answer exists (the stream watchdog may clear it while the answer
    is still on its way), so both sides are polled and every change of either is kept for the report.
    """
    began = time.monotonic()
    timeline: list[str] = []
    previous = ""
    while time.monotonic() - began < timeout_sec:
        try:
            raw = client.evaluate(page, _ANSWER_STATE_JS, timeout_sec=15.0)
        except (RuntimeError, TimeoutError, OSError) as failure:
            raw = {"unreachable": type(failure).__name__}
        shown = raw if isinstance(raw, dict) else {}
        replies = completed_assistant_replies(stored_messages(chat_id, api_url))
        row = f"page={json.dumps(shown, sort_keys=True)} stored_complete_answers={len(replies)}"
        if row != previous:
            timeline.append(f"+{time.monotonic() - began:.0f}s {row}")
            previous = row
        last_length = shown.get("lastLength")
        page_ready = not page_settled or (shown.get("loading") is False and isinstance(last_length, int) and last_length > 0)
        if len(replies) >= count and page_ready:
            print(f"E2E_ANSWER_TIMELINE[{count}]: {timeline}", flush=True)
            return replies[count - 1]
        time.sleep(1.0)
    pytest.fail(f"answer {count} not stored within {timeout_sec}s\ntimeline: {timeline}\n{_follow_up_report(client, page)}")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_finished_answer_offers_follow_ups_and_a_click_asks_one(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    suffix = uuid.uuid4().hex[:8]
    agent_id = _create_agent(api_url, suffix)
    e2e_resource_ledger.register("agent", agent_id)
    chat_id = f"e2efollowup{suffix}"
    _create_chat(api_url, chat_id, agent_id)
    e2e_resource_ledger.register("chat", chat_id)
    log_offset = snapshot_backend_log_offset(api_url)
    probe = SkillChat(skill_name="", agent_id=agent_id, chat_id=chat_id, out=tmp_path, log_offset=log_offset)
    chat_url = f"{ui_url.rstrip('/')}{probe.ui_path}"

    def agent_bound(client: ChromeMcpClient, page: McpPage) -> None:
        applied = wait_for_state(client, page, _call(_AGENT_BOUND_JS, agent_id), timeout_sec=90.0, page_url=chat_url)
        assert applied.get("ready") is True, applied
        client.evaluate(page, _PAGE_PULSE_JS, timeout_sec=15.0)

    def check_follow_ups(client: ChromeMcpClient, page: McpPage) -> None:
        first = _wait_for_answer(client, page, chat_id, api_url, count=1, page_settled=False, timeout_sec=240.0)
        print(f"E2E_ASSISTANT_REPLY[{chat_id}]: {first[:300]}", flush=True)

        try:
            chips = wait_for_state(client, page, _CHIPS_JS, timeout_sec=90.0, page_url=chat_url)
        except AssertionError as failure:
            pytest.fail(f"no follow-up question appeared under the answer: {failure}\n{_follow_up_report(client, page)}")
        texts = chips.get("texts")
        assert isinstance(texts, list) and 1 <= len(texts) <= 5, chips
        assert all(isinstance(text, str) and text.strip() for text in texts), chips
        print(f"E2E_FOLLOW_UPS: {json.dumps(texts, ensure_ascii=False)}", flush=True)

        clicked = client.evaluate(page, _CLICK_CHIP_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked
        # The click is the user asking that question: the server stores it as the next user message.
        wait_user_message_persisted(chat_id, api_url, str(clicked["text"]))
        answer = _wait_for_answer(client, page, chat_id, api_url, count=2, page_settled=True, timeout_sec=240.0)
        print(f"E2E_CLICKED_ANSWER: {answer[:300]}", flush=True)

    # The private backend and its log are reaped at teardown, so a failed turn has to print its own server evidence.
    with dump_backend_log_on_failure(api_url), _backend_errors_on_failure(api_url):
        drive_chat_turn(
            ui_url,
            probe,
            _QUESTION,
            invoke_skill=False,
            before_send=agent_bound,
            while_open=check_follow_ups,
        )
