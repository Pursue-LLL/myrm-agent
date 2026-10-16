"""Chrome E2E: the catchup inbox follows what the user has and has not seen, in a real browser.

Three scenarios, none of which involves a model:

1. A reply stored while the user is looking at a chat is not reported as missed once the user switches to another
   chat: the page has to stamp the chat as read on the way out. The other signals of stopping to look (blur, hidden,
   focus back) are swallowed in the page, so the stamp comes from the switch itself. The hook's cleanup is not the only
   source of that stamp (the open chat's effect also re-runs while the view changes over), so what this scenario pins
   down is the outcome; the cleanup path alone is covered by the hook's unit tests.
2. A reply that arrived while the user was elsewhere shows up in the inbox on the home page (badge, card with the
   reply); opening it from the card marks it read.
3. The same card can be dismissed with "mark as read" without opening the chat.

Formal run::

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
_REPLY = "The quarterly report is ready: revenue is up 12 percent."

_HYDRATED_JS = """((chatId) => {
  const state = window.__myrmChatStore?.getState?.();
  const ready = state?.chatId === chatId && Boolean(state?.isMessagesLoaded) && (state?.messages?.length ?? 0) >= 2;
  return { ready, chatId: state?.chatId ?? null, messages: state?.messages?.length ?? 0, path: location.pathname };
})"""

# What the read mark sees: the same condition as `isUserPresent()` in the app.
_PRESENCE_JS = """(() => ({ present: !document.hidden && document.hasFocus() }))()"""


_AT_HOME_JS = """(() => ({ ready: location.pathname === '/', path: location.pathname }))()"""

# Stopping to look has three other signals (blur, hidden, focus back). They are swallowed before the app sees them,
# so a stamp on leaving comes from the switch itself; each signal is covered on its own by the hook's unit tests.
_ISOLATE_LEAVE_PATH_JS = """(() => {
  const swallow = (event) => event.stopImmediatePropagation();
  window.addEventListener('blur', swallow, true);
  window.addEventListener('focus', swallow, true);
  document.addEventListener('visibilitychange', swallow, true);
  return { isolated: true };
})()"""

# Which conversations the page stamped as read.
_SPY_READ_STAMPS_JS = """(() => {
  window.__MYRM_READ_STAMPS__ = [];
  const nativeFetch = window.fetch;
  window.fetch = function (input, init) {
    const url = typeof input === 'string' ? input : input?.url ?? String(input);
    const match = /\\/chats\\/([^/?]+)\\/read(?:\\?|$)/.exec(url);
    if (match && (init?.method ?? 'GET').toUpperCase() === 'POST') window.__MYRM_READ_STAMPS__.push({ id: match[1], path: location.pathname, at: Math.round(performance.now()) });
    return nativeFetch.apply(this, arguments);
  };
  return { installed: true };
})()"""

_READ_STAMPS_JS = """(() => [...(window.__MYRM_READ_STAMPS__ ?? [])])()"""

# The inbox trigger in the sidebar, with the count its label carries.
_TRIGGER_JS = """(() => {
  const trigger = Array.from(document.querySelectorAll('[data-testid="catchup-inbox-trigger"]')).find(
    (el) => el.offsetParent !== null,
  );
  const count = Number((trigger?.getAttribute('aria-label') ?? '').match(/\\d+/)?.[0] ?? 0);
  return { ready: Boolean(trigger), count };
})()"""

_CLICK_TRIGGER_JS = """(() => {
  const trigger = Array.from(document.querySelectorAll('[data-testid="catchup-inbox-trigger"]')).find(
    (el) => el.offsetParent !== null,
  );
  if (!trigger) return { clicked: false };
  trigger.click();
  return { clicked: true };
})()"""


def _card_js(chat_id: str) -> str:
    return f"""(() => {{
  const card = document.querySelector('[data-testid="catchup-brief-card"][data-chat-id="{chat_id}"]');
  return {{ ready: Boolean(card), text: card?.innerText ?? '' }};
}})()"""


def _no_card_js(chat_id: str) -> str:
    return f"""(() => {{
  const card = document.querySelector('[data-testid="catchup-brief-card"][data-chat-id="{chat_id}"]');
  return {{ ready: !card }};
}})()"""


def _click_in_card_js(chat_id: str, test_id: str) -> str:
    return f"""(() => {{
  const card = document.querySelector('[data-testid="catchup-brief-card"][data-chat-id="{chat_id}"]');
  const button = card?.querySelector('[data-testid="{test_id}"]');
  if (!button) return {{ clicked: false }};
  button.click();
  return {{ clicked: true }};
}})()"""


def _post_chat(api_url: str, chat_id: str, title: str, reply_at: datetime) -> None:
    """Create or replace a conversation: a question 5 minutes ago and a reply at `reply_at`."""
    question_at = datetime.now(UTC).replace(microsecond=0, tzinfo=None) - timedelta(minutes=5)
    messages = [
        ("user", "Summarise the quarterly report", question_at),
        ("assistant", _REPLY, reply_at),
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


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _mark_read(api_url: str, chat_id: str) -> None:
    marked = http_json("POST", f"{api_url}/api/v1/chats/{chat_id}/read")
    assert isinstance(marked, dict) and marked.get("success") is True, marked


def _unseen_chat_ids(api_url: str) -> set[str]:
    response = http_json("GET", f"{api_url}/api/v1/chats/catchup")
    assert isinstance(response, dict), response
    data = response["data"]
    assert isinstance(data, dict), response
    briefs = data["briefs"]
    assert isinstance(briefs, list), response
    return {str(brief["chat_id"]) for brief in briefs}


def _seed_unseen_chat(api_url: str, title: str) -> str:
    """A conversation whose newest reply is newer than the user's last presence."""
    chat_id = f"e2ecatchup{uuid.uuid4().hex[:8]}"
    _post_chat(api_url, chat_id, title, _utc_now() - timedelta(minutes=4))
    _mark_read(api_url, chat_id)
    time.sleep(1.5)
    _post_chat(api_url, chat_id, title, _utc_now())
    assert chat_id in _unseen_chat_ids(api_url), "the reply newer than the read mark must count as unseen"
    return chat_id


def _wait_until(api_url: str, chat_id: str, *, unseen: bool) -> float:
    started = time.monotonic()
    while time.monotonic() - started < _STAMP_TIMEOUT_SEC:
        if (chat_id in _unseen_chat_ids(api_url)) is unseen:
            return time.monotonic() - started
        time.sleep(0.5)
    state = "still read" if unseen else "still unseen"
    raise AssertionError(f"{chat_id} is {state} {_STAMP_TIMEOUT_SEC:.0f}s later")


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


@contextmanager
def _ready_page(ui_url: str, path: str, hydrated_chat_id: str | None) -> Iterator[tuple[ChromeMcpClient, McpPage]]:
    """Open `path` in the E2E Chrome and wait until the app (and the conversation, if any) is on screen."""
    page_url = f"{ui_url}{path}"
    with open_mcp_page(page_url, timeout_ms=_PAGE_TIMEOUT_MS) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=page_url)
        wait_for_react_e2e_bridge(client, page, timeout_sec=240.0, page_url=page_url)
        if hydrated_chat_id is not None:
            wait_for_state(
                client, page, f"({_HYDRATED_JS})({json.dumps(hydrated_chat_id)})", timeout_sec=300.0, page_url=page_url
            )
        yield client, page


def _assert_present(client: ChromeMcpClient, page: McpPage) -> None:
    result = client.evaluate(page, _PRESENCE_JS, timeout_sec=15.0)
    assert isinstance(result, dict), result
    print(f"E2E_CATCHUP_PRESENT: {result['present']}", flush=True)
    assert result["present"] is True, "the E2E tab must count as present, otherwise the presence logic is not exercised"


def _open_inbox_and_find_card(client: ChromeMcpClient, page: McpPage, ui_url: str, chat_id: str) -> dict[str, object]:
    home_url = f"{ui_url}/"
    trigger = wait_for_state(client, page, _TRIGGER_JS, timeout_sec=120.0, page_url=home_url)
    print(f"E2E_CATCHUP_BADGE: {trigger['count']}", flush=True)
    assert isinstance(trigger["count"], int) and trigger["count"] >= 1, trigger
    clicked = client.evaluate(page, _CLICK_TRIGGER_JS, timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked["clicked"] is True, clicked
    return wait_for_state(client, page, _card_js(chat_id), timeout_sec=60.0, page_url=home_url)


def _click_in_card(client: ChromeMcpClient, page: McpPage, chat_id: str, test_id: str) -> None:
    clicked = client.evaluate(page, _click_in_card_js(chat_id, test_id), timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked["clicked"] is True, f"no {test_id} on the card of {chat_id}: {clicked}"


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_reply_that_arrives_while_watching_is_marked_read_when_the_user_leaves() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    watched_id = f"e2ewatched{uuid.uuid4().hex[:8]}"
    _post_chat(api_url, watched_id, "Catchup watched chat", _utc_now() - timedelta(minutes=4))
    other_id = _seed_unseen_chat(api_url, f"Catchup other chat {uuid.uuid4().hex[:6]}")
    assert watched_id not in _unseen_chat_ids(api_url), "the seeded conversation must start read"

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{watched_id}")
    warm_ui_route(f"/{other_id}")

    watched_url = f"{ui_url}/{watched_id}"
    with _ready_page(ui_url, f"/{watched_id}", watched_id) as (client, page), _page_in_focus(str(page.target_id)):
        _assert_present(client, page)
        # The user leaves through the inbox card of the other conversation: a switch straight from one conversation
        # to another, the case only the leave-time stamp covers (the open one was stamped when it opened).
        wait_for_state(client, page, _TRIGGER_JS, timeout_sec=120.0, page_url=watched_url)
        client.evaluate(page, _ISOLATE_LEAVE_PATH_JS, timeout_sec=15.0)
        client.evaluate(page, _SPY_READ_STAMPS_JS, timeout_sec=15.0)

        # The user is looking at the chat, so it is read up to now; a reply stored afterwards is on screen but unseen.
        _mark_read(api_url, watched_id)
        time.sleep(1.5)
        _post_chat(api_url, watched_id, "Catchup watched chat", _utc_now())
        unseen_while_watching = watched_id in _unseen_chat_ids(api_url)
        print(f"E2E_CATCHUP_UNSEEN_WHILE_WATCHING: {unseen_while_watching}", flush=True)
        assert unseen_while_watching, "the reply that landed after the read mark must count as unseen"

        stamps_before = client.evaluate(page, _READ_STAMPS_JS, timeout_sec=15.0)
        assert stamps_before == [], f"something stamped the chat while the user was still on it: {stamps_before}"
        clicked = client.evaluate(page, _CLICK_TRIGGER_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked["clicked"] is True, clicked
        wait_for_state(client, page, _card_js(other_id), timeout_sec=60.0, page_url=watched_url)
        _click_in_card(client, page, other_id, "catchup-view-chat")
        other_url = f"{ui_url}/{other_id}"
        wait_for_state(client, page, f"({_HYDRATED_JS})({json.dumps(other_id)})", timeout_sec=240.0, page_url=other_url)

        stamps_after = client.evaluate(page, _READ_STAMPS_JS, timeout_sec=15.0)
        print(f"E2E_CATCHUP_PAGE_STAMPS_AFTER_LEAVING: {stamps_after}", flush=True)
        assert watched_id in [stamp["id"] for stamp in stamps_after], f"leaving the chat did not stamp it: {stamps_after}"
        seconds = _wait_until(api_url, watched_id, unseen=False)
        print(f"E2E_CATCHUP_READ_AFTER_LEAVING: {seconds:.1f}s", flush=True)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_reply_that_arrived_while_away_shows_in_the_inbox_and_opening_it_marks_it_read() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    title = f"Catchup away chat {uuid.uuid4().hex[:6]}"
    chat_id = _seed_unseen_chat(api_url, title)

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")

    with _ready_page(ui_url, "/", None) as (client, page), _page_in_focus(str(page.target_id)):
        _assert_present(client, page)
        card = _open_inbox_and_find_card(client, page, ui_url, chat_id)
        text = str(card["text"])
        print(f"E2E_CATCHUP_CARD: {text[:160]!r}", flush=True)
        assert title in text and "revenue is up 12 percent" in text, f"the card must show the chat and its reply: {text}"
        # The chat was updated seconds ago; a timestamp read as local time instead of UTC shows it hours old.
        assert "小时" not in text and "hour" not in text.lower(), f"the card dates the activity hours ago: {text}"

        _click_in_card(client, page, chat_id, "catchup-view-chat")
        wait_for_state(
            client, page, f"({_HYDRATED_JS})({json.dumps(chat_id)})", timeout_sec=240.0, page_url=f"{ui_url}/{chat_id}"
        )
        seconds = _wait_until(api_url, chat_id, unseen=False)
        print(f"E2E_CATCHUP_READ_AFTER_OPENING: {seconds:.1f}s", flush=True)


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_mark_as_read_dismisses_the_card_without_opening_the_chat() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url().rstrip("/")
    chat_id = _seed_unseen_chat(api_url, f"Catchup dismissed chat {uuid.uuid4().hex[:6]}")

    prepare_e2e_ui_session(api_url)
    warm_ui_route("/")

    with _ready_page(ui_url, "/", None) as (client, page), _page_in_focus(str(page.target_id)):
        _assert_present(client, page)
        _open_inbox_and_find_card(client, page, ui_url, chat_id)

        _click_in_card(client, page, chat_id, "catchup-mark-read")
        wait_for_state(client, page, _no_card_js(chat_id), timeout_sec=60.0, page_url=f"{ui_url}/")
        seconds = _wait_until(api_url, chat_id, unseen=False)
        print(f"E2E_CATCHUP_READ_AFTER_DISMISSING: {seconds:.1f}s", flush=True)
        path = client.evaluate(page, _AT_HOME_JS, timeout_sec=15.0)
        assert isinstance(path, dict) and path["ready"] is True, f"dismissing must not navigate: {path}"
