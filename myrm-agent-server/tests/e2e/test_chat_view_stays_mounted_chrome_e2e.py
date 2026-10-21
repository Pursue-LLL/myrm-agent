"""Chrome E2E: an open conversation stays mounted while the user types and while nothing happens.

Re-creating the chat view (message list, composer and everything that fetches when it mounts) is invisible in a
screenshot, but it drops the composer's focus, resets the scroll position and repeats a dozen API calls. The view is
opened on a stored conversation, left alone for a few seconds, then a question is typed one key at a time.

No model is involved. Formal run::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_chat_view_stays_mounted_chrome_e2e.py
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
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

_QUESTION = "And what about the sunset?"
_SETTLE_SEC = 3.0
_IDLE_SEC = 12.0
_PAGE_TIMEOUT_MS = 180_000

# The conversation is on screen with its messages and the composer belongs to React (the server-rendered textarea
# does not take input).
_HYDRATED_JS = """((chatId) => {
  const state = window.__myrmChatStore?.getState?.();
  const input = document.querySelector('textarea[data-chat-input]');
  const ready = state?.chatId === chatId && Boolean(state?.isMessagesLoaded) && (state?.messages?.length ?? 0) >= 2
    && Boolean(input) && Object.keys(input).some((key) => key.startsWith('__reactProps$'));
  return { ready, chatId: state?.chatId ?? null, messages: state?.messages?.length ?? 0 };
})"""

# Counts, from now on: composers that were re-created, chat-store updates and API calls (not the pollers).
_WATCH_JS = """(() => {
  const watch = (window.__MYRM_VIEW_WATCH__ = { composerNodes: 0, storeUpdates: 0, calls: [] });
  let lastInput = document.querySelector('textarea[data-chat-input]');
  new MutationObserver(() => {
    const input = document.querySelector('textarea[data-chat-input]');
    if (input && input !== lastInput) {
      lastInput = input;
      watch.composerNodes += 1;
    }
  }).observe(document.body, { childList: true, subtree: true });
  window.__myrmChatStore.subscribe(() => { watch.storeUpdates += 1; });
  const nativeFetch = window.fetch;
  window.fetch = function (input) {
    const url = typeof input === 'string' ? input : input?.url ?? String(input);
    const path = url.replace(/^https?:\\/\\/[^/]+/, '').replace(/^\\/api\\/v1/, '').split('?')[0];
    if (!/health|stream/.test(path)) watch.calls.push(path);
    return nativeFetch.apply(this, arguments);
  };
  return { ok: true };
})()"""

_READ_WATCH_JS = """(() => {
  const watch = window.__MYRM_VIEW_WATCH__;
  const perEndpoint = {};
  for (const path of watch.calls) perEndpoint[path] = (perEndpoint[path] ?? 0) + 1;
  const busiest = Object.entries(perEndpoint).sort((a, b) => b[1] - a[1]).slice(0, 8);
  return {
    composerNodes: watch.composerNodes,
    storeUpdates: watch.storeUpdates,
    apiCalls: watch.calls.length,
    busiestEndpoints: Object.fromEntries(busiest),
  };
})()"""

# One key at a time, as the keyboard delivers it: a key goes to the focused element only, so when the composer was
# re-created and lost focus, the key is lost.
_TYPE_KEYS_JS = """(async (text) => {
  const find = () => document.querySelector('textarea[data-chat-input]');
  find()?.focus();
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
  let lostKeys = 0;
  let recreated = 0;
  for (const key of text) {
    const target = document.activeElement;
    if (!(target instanceof HTMLTextAreaElement) || !target.hasAttribute('data-chat-input')) {
      lostKeys += 1;
      continue;
    }
    setter.call(target, target.value + key);
    target.dispatchEvent(new Event('input', { bubbles: true }));
    await new Promise((resolve) => setTimeout(resolve, 80));
    if (find() !== target) recreated += 1;
  }
  const composer = find();
  return { value: composer?.value ?? null, lostKeys, recreated, focused: document.activeElement === composer };
})"""


def _read_watch(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    report = client.evaluate(page, _READ_WATCH_JS, timeout_sec=15.0)
    assert isinstance(report, dict), report
    return report


def _calls_to(report: dict[str, object], path: str) -> int:
    endpoints = report.get("busiestEndpoints")
    assert isinstance(endpoints, dict), report
    calls = endpoints.get(path, 0)
    assert isinstance(calls, int), report
    return calls


def _seed_conversation(api_url: str) -> str:
    chat_id = f"e2emounted{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    turns = [("Why is the sky blue?", "Sunlight scatters off air molecules, and blue light scatters the most.")]
    messages: list[dict[str, object]] = []
    for index, (question, answer) in enumerate(turns):
        for offset, (role, content) in enumerate((("user", question), ("assistant", answer))):
            messages.append(
                {
                    "messageId": f"msg-{role}-{chat_id}-{index}",
                    "chatId": chat_id,
                    "role": role,
                    "content": content,
                    "createdAt": (now + timedelta(seconds=index * 2 + offset)).isoformat(),
                }
            )
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Chat view stays mounted",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": messages,
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created
    return chat_id


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(420)
def test_open_conversation_is_not_re_created_while_idle_or_typing() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    chat_id = _seed_conversation(api_url)
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(chat_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
        wait_for_state(client, page, f"({_HYDRATED_JS})({json.dumps(chat_id)})", timeout_sec=150.0, page_url=chat_url)

        time.sleep(_SETTLE_SEC)
        client.evaluate(page, _WATCH_JS, timeout_sec=15.0)
        time.sleep(_IDLE_SEC)
        idle = _read_watch(client, page)
        print(f"E2E_VIEW_IDLE[{_IDLE_SEC:.0f}s]: {json.dumps(idle)}", flush=True)

        typed = client.evaluate(page, f"({_TYPE_KEYS_JS})({json.dumps(_QUESTION)})", timeout_sec=60.0)
        after_typing = _read_watch(client, page)
        print(f"E2E_VIEW_TYPING: {json.dumps({'typed': typed, 'watch': after_typing})}", flush=True)

    assert isinstance(typed, dict), typed
    assert idle["composerNodes"] == 0, f"the composer was re-created {idle['composerNodes']}x while idle: {idle}"
    repeated = _calls_to(idle, "/agents/templates")
    assert repeated <= 1, f"mount-time fetches ran {repeated}x while idle: {idle}"
    assert typed["lostKeys"] == 0 and typed["recreated"] == 0 and typed["focused"] is True, typed
    assert typed["value"] == _QUESTION, typed
    assert after_typing["composerNodes"] == idle["composerNodes"], f"typing re-created the composer: {after_typing}"
