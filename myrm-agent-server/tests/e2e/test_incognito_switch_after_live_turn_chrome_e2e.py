"""Chrome E2E: after a real model turn, switching incognito starts a fresh chat.

This lane is LIVE because it drives the real model: a conversation is opened, the user asks a question, the agent
streams a reply, and only then does the switch get used. That ordering is what a user actually does — they finish a
conversation, then decide to ask something privately — and it is also the state where the switch used to silently
keep the old chat, because its row already existed as a normal one.

Formal run::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_incognito_switch_after_live_turn_chrome_e2e.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import UTC, datetime

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from cdp_chat.support import (  # noqa: E402
    fetch_chat_messages,
    wait_e2e_provider_ready,
)

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
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
from tests.support.e2e_provider_seed import seed_live_e2e_providers  # noqa: E402

_TOGGLE_LABELS = ("Incognito Mode", "无痕模式", "無痕模式", "シークレットモード", "시크릿 모드", "Inkognito-Modus")

_FIND_TOGGLE = """const labels = %s;
  const toggle = Array.from(document.querySelectorAll('button[aria-pressed]')).find(
    (el) => labels.includes(el.getAttribute('aria-label') || '') && el.offsetParent !== null,
  );""" % list(_TOGGLE_LABELS)

_QUESTION = "In one short sentence, what is the capital of France?"

# Attach the E2E bridge to the seeded conversation, then wait for its composer to exist.
_ATTACH_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) return { ok: false, err: 'no-bridge' };
  await bridge.attachToChat(%s);
  const deadline = Date.now() + 30_000;
  while (Date.now() < deadline) {
    if (document.querySelector('[data-chat-input]')) break;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  const snap = bridge.turnSnapshot?.() ?? {};
  return { ok: snap.chatId === %s, snap };
})()"""

# Ask the real model. The bridge submits exactly like the composer does.
_SEND_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return { ok: false, err: 'no-sendChatMessage' };
  bridge.setActionMode?.('agent');
  return await bridge.sendChatMessage(%s, {
    waitForStreamCompletion: false,
    preserveActionMode: true,
  });
})()""" % json.dumps(_QUESTION)

# A click that lands before React hydrates is lost, so both the composer and the toggle must carry handlers first,
# and the turn must have finished (a live turn keeps `loading` true).
_READY_FOR_SWITCH = f"""(() => {{
  {_FIND_TOGGLE}
  const store = window.__myrmChatStore;
  const input = document.querySelector('textarea');
  const isHydrated = (el) => !!el && Object.keys(el).some((key) => key.startsWith('__reactProps'));
  if (!store || !isHydrated(toggle) || !isHydrated(input)) return {{ ready: false }};
  const state = store.getState();
  return {{
    ready: !state.loading && state.messages.length > 0,
    pressed: toggle.getAttribute('aria-pressed'),
    chatId: state.chatId ?? null,
    messages: state.messages.length,
  }};
}})()"""

_CLICK_TOGGLE = f"""(() => {{
  {_FIND_TOGGLE}
  if (!toggle) return {{ clicked: false }};
  toggle.click();
  return {{ clicked: true }};
}})()"""

# `ready` waits only for the route and the id to change, so the assertions stay independent of the wait.
_SWITCHED = """(() => {
  const store = window.__myrmChatStore;
  if (!store) return { ready: false };
  const state = store.getState();
  return {
    ready: location.pathname === '/' && state.chatId !== %s,
    path: location.pathname,
    incognito: state.incognitoMode === true,
    chatId: state.chatId ?? null,
    messages: state.messages.length,
  };
})()"""


def _seed_conversation(api_url: str) -> str:
    chat_id = f"e2elive{uuid.uuid4().hex[:8]}"
    created = http_json(
        "POST",
        f"{api_url}/api/v1/chats/",
        body={
            "chat_id": chat_id,
            "title": "Incognito after a live turn",
            "action_mode": "agent",
            "is_incognito": False,
            "messages": [
                {
                    "messageId": f"msg-open-{chat_id}",
                    "chatId": chat_id,
                    "role": "user",
                    "content": "Opening the conversation.",
                    "createdAt": datetime.now(UTC).replace(microsecond=0).isoformat(),
                }
            ],
        },
    )
    assert isinstance(created, dict) and created.get("success") is True, created
    return chat_id


def _wait_assistant_reply(chat_id: str, api_url: str, *, timeout_sec: float = 240.0) -> dict[str, object]:
    """Poll the stored messages until the live model's assistant reply lands."""
    deadline = time.monotonic() + timeout_sec
    last: list[dict[str, object]] = []
    while time.monotonic() < deadline:
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_url)
        except OSError:
            messages = []
        last = [m for m in messages if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        assistant = next((m for m in reversed(last) if isinstance(m, dict) and m.get("role") == "assistant"), None)
        if isinstance(assistant, dict):
            content = assistant.get("content") or assistant.get("message") or ""
            if isinstance(content, str) and content.strip():
                return assistant
        time.sleep(3.0)
    pytest.fail(
        f"assistant reply not received within {timeout_sec}s for chat {chat_id}; "
        f"messages={json.dumps(last, ensure_ascii=False)[:600]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_switching_incognito_after_a_live_turn_starts_a_fresh_chat() -> None:
    """A real model answer, then the switch: the chat must change and the mode must stay on."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    prepare_e2e_ui_session(api_url)
    seed_live_e2e_providers(api_url)
    if not wait_e2e_provider_ready(timeout_sec=90.0):
        pytest.fail("Provider not ready — run ./myrm ready --chrome")

    chat_id = _seed_conversation(api_url)
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    warm_ui_route("/")
    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        bridge = wait_for_react_e2e_bridge(client, page, timeout_sec=120.0, page_url=chat_url)
        assert bridge.get("ready") is True, json.dumps(bridge, ensure_ascii=False)

        chat_id_json = json.dumps(chat_id)
        attached = client.evaluate(page, _ATTACH_JS % (chat_id_json, chat_id_json), timeout_sec=60.0)
        assert isinstance(attached, dict) and attached.get("ok") is True, attached

        # The real model answers; only then is the switch used, which is the user's actual ordering.
        sent = client.evaluate(page, _SEND_JS, timeout_sec=60.0)
        assert isinstance(sent, dict) and sent.get("ok") is not False, sent
        reply = _wait_assistant_reply(chat_id, api_url)
        assert str(reply.get("role")) == "assistant", reply
        assert str(reply.get("content") or reply.get("message") or "").strip(), reply

        ready = wait_for_state(client, page, _READY_FOR_SWITCH, timeout_sec=_warm_ui_parallel_wait_sec(120.0))
        assert ready.get("pressed") == "false", ready

        assert client.evaluate(page, _CLICK_TOGGLE).get("clicked") is True
        state = wait_for_state(client, page, _SWITCHED % chat_id_json, timeout_sec=90.0)

        assert state.get("incognito") is True, state
        assert state.get("chatId") not in (None, chat_id), state
        assert state.get("messages") == 0, state
