"""Chrome E2E: the incognito switch always starts a fresh chat.

The switch is client state, so this lane is SHARED+NAMESPACE_WRITE. Each case opens a real chat by URL and drives
the real toggle, covering the three transitions the fix is about:

* an ordinary conversation  -> incognito on  starts a new chat and keeps the mode
* an existing empty row      -> incognito on  starts a new chat (the row could never become incognito)
* an incognito chat          -> incognito off starts a new chat

Formal run::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_incognito_switch_starts_fresh_chat_chrome_e2e.py
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_TOGGLE_LABELS = ("Incognito Mode", "无痕模式", "無痕模式", "シークレットモード", "시크릿 모드", "Inkognito-Modus")

_FIND_TOGGLE = """const labels = %s;
  const toggle = Array.from(document.querySelectorAll('button[aria-pressed]')).find(
    (el) => labels.includes(el.getAttribute('aria-label') || '') && el.offsetParent !== null,
  );""" % list(_TOGGLE_LABELS)

_CLICK_TOGGLE = f"""(() => {{
  {_FIND_TOGGLE}
  if (!toggle) return {{ clicked: false }};
  toggle.click();
  return {{ clicked: true }};
}})()"""

# A click that lands before React hydrates is lost. Wait for the toggle and the composer to carry React handlers, and
# for the store to hold the conversation the route opened — clicking while it is still loading would race the handler.
_SWITCH_READY_TEMPLATE = """(() => {
  %(find_toggle)s
  const store = window.__myrmChatStore;
  const input = document.querySelector('textarea');
  const isHydrated = (el) => !!el && Object.keys(el).some((key) => key.startsWith('__reactProps'));
  if (!store || !isHydrated(toggle) || !isHydrated(input)) return { ready: false };
  const state = store.getState();
  return {
    ready: state.chatId === %(chat_id)s && !state.loading,
    pressed: toggle.getAttribute('aria-pressed'),
    chatId: state.chatId ?? null,
  };
})()"""


def _switch_ready(chat_id: str) -> str:
    """The readiness probe for a conversation route, with the opened chat id baked in.

    ``str.replace`` rather than ``%`` formatting: the snippet is JavaScript and may legitimately contain ``%``.
    """
    return _SWITCH_READY_TEMPLATE.replace("%(find_toggle)s", _FIND_TOGGLE).replace("%(chat_id)s", f'"{chat_id}"')


def _switched(expect_incognito: bool, original_chat_id: str) -> str:
    """The settled probe once the switch has run.

    ``ready`` only waits for the route to reach ``/`` and for the store to leave the chat that was open, so the
    assertions stay independent of the wait instead of being pre-satisfied by it.
    """
    return """(() => {
  const store = window.__myrmChatStore;
  if (!store) return { ready: false };
  const state = store.getState();
  return {
    ready: location.pathname === '/' && state.chatId !== %(original)s,
    path: location.pathname,
    incognito: state.incognitoMode === true,
    chatId: state.chatId ?? null,
    messages: state.messages.length,
    expected: %(expected)s,
  };
})()""" % {"original": f'"{original_chat_id}"', "expected": "true" if expect_incognito else "false"}


def _seed_chat_with_id(api_url: str, *, chat_id: str, messages: list[dict[str, object]], incognito: bool, title: str) -> str:
    """Create one chat row, so the seed and the assertions agree on the same id."""
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": title,
            "action_mode": "agent",
            "is_incognito": incognito,
            "messages": messages,
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created
    return chat_id


def _seed_chat(api_url: str, *, messages: list[dict[str, object]], incognito: bool, title: str) -> str:
    return _seed_chat_with_id(
        api_url,
        chat_id=f"e2eswitch{uuid.uuid4().hex[:8]}",
        messages=messages,
        incognito=incognito,
        title=title,
    )


def _conversation_messages(chat_id: str) -> list[dict[str, object]]:
    now = datetime.now(UTC).replace(microsecond=0)
    return [
        {
            "messageId": f"msg-{role}-{chat_id}",
            "chatId": chat_id,
            "role": role,
            "content": content,
            "createdAt": (now + timedelta(seconds=index)).isoformat(),
        }
        for index, (role, content) in enumerate(
            (("user", "Where does the river start?"), ("assistant", "At the spring above the village."))
        )
    ]


def _open_and_switch(chat_id: str, *, expect_incognito: bool) -> dict[str, object]:
    """Open ``chat_id`` by URL, click the real toggle, and return the settled state."""
    ui_url = get_e2e_ui_url()
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=chat_url)

        ready = wait_for_state(client, page, _switch_ready(chat_id), timeout_sec=_warm_ui_parallel_wait_sec(150.0))
        assert ready.get("pressed") == ("true" if expect_incognito else "false"), ready

        assert client.evaluate(page, _CLICK_TOGGLE).get("clicked") is True
        return wait_for_state(client, page, _switched(not expect_incognito, chat_id), timeout_sec=90.0)


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_incognito_opens_a_new_chat_and_keeps_the_mode() -> None:
    api_url = get_e2e_api_url()
    chat_id = f"e2eswitch{uuid.uuid4().hex[:8]}"
    seeded = _seed_chat_with_id(
        api_url,
        chat_id=chat_id,
        messages=_conversation_messages(chat_id),
        incognito=False,
        title="Incognito switch starts a fresh chat",
    )
    prepare_e2e_ui_session(api_url)

    state = _open_and_switch(seeded, expect_incognito=False)

    assert state.get("incognito") is True, state
    assert state.get("chatId") not in (None, seeded), state
    assert state.get("messages") == 0, state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_incognito_on_an_empty_chat_row_also_starts_a_fresh_chat() -> None:
    """The row exists but holds no messages — the state ``/focus`` leaves behind.

    Keeping that id would leave the user in a chat the server never treats as incognito, because its row already
    says otherwise. The switch must mint a new id even though there is nothing on screen.
    """
    api_url = get_e2e_api_url()
    seeded = _seed_chat(api_url, messages=[], incognito=False, title="Empty chat row")
    prepare_e2e_ui_session(api_url)

    state = _open_and_switch(seeded, expect_incognito=False)

    assert state.get("incognito") is True, state
    assert state.get("chatId") not in (None, seeded), state


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_incognito_off_from_an_incognito_chat_starts_a_normal_chat() -> None:
    """The off direction: an incognito chat must not silently become a normal one either."""
    api_url = get_e2e_api_url()
    seeded = _seed_chat(api_url, messages=[], incognito=True, title="Incognito chat")
    prepare_e2e_ui_session(api_url)

    state = _open_and_switch(seeded, expect_incognito=True)

    assert state.get("incognito") is False, state
    assert state.get("chatId") not in (None, seeded), state
