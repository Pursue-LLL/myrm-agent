"""Chrome E2E: the incognito switch starts a fresh chat from a conversation route.

The switch is client state, so this lane is SHARED+READ. It reproduces the sequence the fix is about: open a
real conversation by URL, turn incognito on, and assert that the window lands on `/`, the chat id is a new one
(not the conversation that was open), and the flag stays on after the route the switch itself triggers mounts.

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

# A click that lands before React hydrates is lost. Wait for the toggle and the composer to carry React handlers,
# and for the store to hold the conversation the route opened — clicking while it is still loading would race the
# handler and let the click land on a page that has not wired it up yet.
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
    probe = _SWITCH_READY_TEMPLATE.replace("%(find_toggle)s", _FIND_TOGGLE)
    return probe.replace("%(chat_id)s", f'"{chat_id}"')


_CLICK_TOGGLE = f"""(() => {{
  {_FIND_TOGGLE}
  if (!toggle) return {{ clicked: false }};
  toggle.click();
  return {{ clicked: true }};
}})()"""

# Reports the observable state; `ready` only waits for the window to land on `/`, so the assertions below stay
# independent of the wait instead of being pre-satisfied by it.
_SWITCHED_STATE = """(() => {
  const store = window.__myrmChatStore;
  if (!store) return { ready: false };
  const state = store.getState();
  return {
    ready: location.pathname === '/',
    path: location.pathname,
    incognito: state.incognitoMode === true,
    chatId: state.chatId ?? null,
    messages: state.messages.length,
  };
})()"""


def _seed_conversation(api_url: str) -> str:
    chat_id = f"e2eswitch{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(microsecond=0)
    messages: list[dict[str, object]] = [
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
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Incognito switch starts a fresh chat",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": messages,
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created
    return chat_id


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_incognito_opens_a_new_chat_and_keeps_the_mode() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    chat_id = _seed_conversation(api_url)
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=chat_url)

        ready = wait_for_state(client, page, _switch_ready(chat_id), timeout_sec=_warm_ui_parallel_wait_sec(150.0))
        assert ready.get("pressed") == "false", ready

        assert client.evaluate(page, _CLICK_TOGGLE).get("clicked") is True
        state = wait_for_state(client, page, _SWITCHED_STATE, timeout_sec=90.0)

        assert state.get("incognito") is True, state
        assert state.get("chatId") not in (None, chat_id), state
        assert state.get("messages") == 0, state
