"""Chrome E2E: a reply that lands while the user is looking at the chat is not reported as missed afterwards.

The conversation is opened in a real browser (opening it marks it read), then a reply is stored behind the page's
back: the transcript on screen and the server's read mark now disagree, so the inbox would list the chat as unseen.
Going back to the home page is the user "stopping looking" and has to stamp the chat as read again.

No model is involved. Formal run::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_catchup_presence_chrome_e2e.py
"""

from __future__ import annotations

import json
import os
import time
import urllib.request
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from websockets.sync.client import connect

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

_PAGE_TIMEOUT_MS = 180_000
_STAMP_TIMEOUT_SEC = 15.0

_HYDRATED_JS = """((chatId) => {
  const state = window.__myrmChatStore?.getState?.();
  const ready = state?.chatId === chatId && Boolean(state?.isMessagesLoaded) && (state?.messages?.length ?? 0) >= 2;
  return {
    ready,
    chatId: state?.chatId ?? null,
    messages: state?.messages?.length ?? 0,
    path: location.pathname,
    loaded: Boolean(state?.isMessagesLoaded),
    body: (document.body?.innerText ?? '').slice(0, 120),
  };
})"""

# What the read mark sees: the same condition as `isUserPresent()` in the app.
_PRESENCE_JS = """(() => ({ present: !document.hidden && document.hasFocus() }))()"""

# The user leaves the conversation through the sidebar logo, which goes back to the home page. Clicked once: a second
# push while the home route is still compiling would only restart the navigation.
_CLICK_HOME_JS = """(() => {
  const logo = Array.from(document.querySelectorAll('button[aria-label="Home"]')).find((el) => el.offsetParent !== null);
  if (!logo) return { clicked: false, path: location.pathname };
  logo.click();
  return { clicked: true, path: location.pathname };
})()"""

# Which conversations the page stamped as read, so that the stamp can be pinned on leaving rather than on anything else.
_SPY_READ_STAMPS_JS = """(() => {
  window.__MYRM_READ_STAMPS__ = [];
  const nativeFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input?.url ?? String(input);
    const match = /\\/chats\\/([^/?]+)\\/read(?:\\?|$)/.exec(url);
    if (match && (init?.method ?? 'GET').toUpperCase() === 'POST') window.__MYRM_READ_STAMPS__.push(match[1]);
    return nativeFetch.apply(this, arguments);
  };
  return { installed: true };
})()"""

_READ_STAMPS_JS = """(() => [...(window.__MYRM_READ_STAMPS__ ?? [])])()"""

_AT_HOME_JS = """(() => ({ ready: location.pathname === '/', path: location.pathname }))()"""


def _post_chat(api_url: str, chat_id: str, title: str, reply_at: datetime) -> None:
    """Create or replace a conversation: a question 5 minutes ago and a reply at `reply_at`."""
    question_at = datetime.now(UTC).replace(microsecond=0, tzinfo=None) - timedelta(minutes=5)
    messages = [
        ("user", "Summarise the quarterly report", question_at),
        ("assistant", "The quarterly report is ready: revenue is up 12 percent.", reply_at),
    ]
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": title,
            "action_mode": "agent",
            "is_incognito": False,
            "messages": [
                {
                    "messageId": f"msg-{role}-{chat_id}",
                    "chatId": chat_id,
                    "role": role,
                    "content": content,
                    "createdAt": created_at.isoformat(),
                }
                for role, content, created_at in messages
            ],
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created


def _unseen_chat_ids(api_url: str) -> set[str]:
    response = http_json("GET", f"{api_url}/api/v1/chats/catchup")
    assert isinstance(response, dict), response
    data = response["data"]
    assert isinstance(data, dict), response
    briefs = data["briefs"]
    assert isinstance(briefs, list), response
    return {str(brief["chat_id"]) for brief in briefs}


def _wait_until_read(api_url: str, chat_id: str) -> float:
    started = time.monotonic()
    while time.monotonic() - started < _STAMP_TIMEOUT_SEC:
        if chat_id not in _unseen_chat_ids(api_url):
            return time.monotonic() - started
        time.sleep(0.5)
    raise AssertionError(f"{chat_id} is still unseen {_STAMP_TIMEOUT_SEC:.0f}s after the user left it")


@contextmanager
def _page_in_focus(target_id: str) -> Iterator[None]:
    """Keep the tab "focused" as far as the page can tell, for as long as this CDP session stays open.

    The parked E2E window has no OS focus, so `document.hasFocus()` is false and the app rightly treats the user as
    away; the override ends with the session, which is why it wraps the whole scenario.
    """
    port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5) as resp:
        ws_url = next(t["webSocketDebuggerUrl"] for t in json.load(resp) if t["id"] == target_id)
    with connect(ws_url, open_timeout=10, close_timeout=5) as ws:
        ws.send(json.dumps({"id": 1, "method": "Emulation.setFocusEmulationEnabled", "params": {"enabled": True}}))
        while json.loads(ws.recv(timeout=15)).get("id") != 1:
            pass
        yield


def _is_present(client: ChromeMcpClient, page: McpPage) -> bool:
    result = client.evaluate(page, _PRESENCE_JS, timeout_sec=15.0)
    assert isinstance(result, dict), result
    return result["present"] is True


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(900)
def test_reply_that_arrives_while_watching_is_marked_read_when_the_user_leaves() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    suffix = uuid.uuid4().hex[:8]
    watched_id = f"e2ewatched{suffix}"
    old_reply_at = datetime.now(UTC).replace(microsecond=0, tzinfo=None) - timedelta(minutes=4)
    _post_chat(api_url, watched_id, "Catchup watched chat", old_reply_at)
    assert watched_id not in _unseen_chat_ids(api_url), "the seeded conversation must start read"

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{watched_id}")
    warm_ui_route("/")

    with open_mcp_page(f"{ui_url}/{watched_id}", timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=f"{ui_url}/{watched_id}")
        wait_for_react_e2e_bridge(client, page, timeout_sec=240.0, page_url=f"{ui_url}/{watched_id}")
        wait_for_state(
            client, page, f"({_HYDRATED_JS})({json.dumps(watched_id)})", timeout_sec=300.0, page_url=f"{ui_url}/{watched_id}"
        )
        with _page_in_focus(str(page.target_id)):
            _scenario(client, page, api_url, ui_url, watched_id)


def _scenario(client: ChromeMcpClient, page: McpPage, api_url: str, ui_url: str, watched_id: str) -> None:
    present = _is_present(client, page)
    print(f"E2E_CATCHUP_PRESENT: {present}", flush=True)
    assert present, "the E2E tab must count as present, otherwise the presence-end stamp is not exercised"

    client.evaluate(page, _SPY_READ_STAMPS_JS, timeout_sec=15.0)

    # The user is looking at the chat, so it is read up to now; a reply stored afterwards is on screen but unseen.
    marked = http_json("POST", f"{api_url}/api/v1/chats/{watched_id}/read")
    assert isinstance(marked, dict) and marked.get("success") is True, marked
    time.sleep(1.5)
    new_reply_at = datetime.now(UTC).replace(tzinfo=None)
    _post_chat(api_url, watched_id, "Catchup watched chat", new_reply_at)
    unseen_while_watching = watched_id in _unseen_chat_ids(api_url)
    print(f"E2E_CATCHUP_UNSEEN_WHILE_WATCHING: {unseen_while_watching}", flush=True)
    assert unseen_while_watching, "the reply that landed after the opening stamp must count as unseen"

    stamps_before_leaving = client.evaluate(page, _READ_STAMPS_JS, timeout_sec=15.0)
    assert stamps_before_leaving == [], f"something stamped the chat while the user was still on it: {stamps_before_leaving}"
    clicked = client.evaluate(page, _CLICK_HOME_JS, timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked["clicked"] is True, f"no visible Home button in the sidebar: {clicked}"
    wait_for_state(client, page, _AT_HOME_JS, timeout_sec=240.0, page_url=f"{ui_url}/")
    stamps_after_leaving = client.evaluate(page, _READ_STAMPS_JS, timeout_sec=15.0)
    print(f"E2E_CATCHUP_PAGE_STAMPS_AFTER_LEAVING: {stamps_after_leaving}", flush=True)
    assert watched_id in stamps_after_leaving, f"leaving the chat did not stamp it: {stamps_after_leaving}"
    seconds = _wait_until_read(api_url, watched_id)
    print(f"E2E_CATCHUP_READ_AFTER_LEAVING: {seconds:.1f}s", flush=True)
