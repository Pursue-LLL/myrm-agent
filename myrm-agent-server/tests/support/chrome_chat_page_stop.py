"""The Stop button of the chat page, pressed as a user does, and what the page did about it.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers)

[OUTPUT]
- press_stop(): wait until the chat page offers Stop and has attached to the turn, press Stop, and return what the page believed and did (store state when Stop appeared and when it was pressed, cancel requests sent, toasts shown, errors logged)

[POS]
Used by tests/e2e/test_approval_timer_resume_chrome_e2e.py to prove a page attached to a run it did not start can stop that run.
"""

from __future__ import annotations

import time

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, wait_for_state

_STOP_BUTTON_TIMEOUT_SEC = 60.0
# A Stop that reaches the server sends its request within moments; a page that sends nothing stays silent.
_STOP_REACTION_TIMEOUT_SEC = 10.0

# What the chat store holds of the turn: the controller that ends an attached stream, the server-reported status, the loading flag.
_CHAT_STATE_JS = """(() => {
  const chat = window.__myrmChatStore?.getState();
  if (!chat) return null;
  return {
    loading: chat.loading,
    hasAbortController: Boolean(chat.abortController),
    serverStatus: chat.sessionStatuses?.[chat.chatId] ?? null,
    messagesLoaded: chat.isMessagesLoaded,
  };
})()"""

# The chat page's own Stop button: the one control that stops a turn the page is attached to, whoever started it.
_FIND_STOP_JS = """Array.from(document.querySelectorAll('button[aria-label]')).find((b) => /^(Stop|停止)$/.test(b.getAttribute('aria-label') ?? ''))"""

_STOP_APPEARED_JS = f"""(() => ({{ ready: Boolean({_FIND_STOP_JS}), state: {_CHAT_STATE_JS} }}))()"""

# Stop is meant for a turn this page streams: the load of the chat's history shows the button too, before the page has attached.
_ATTACHED_JS = f"""(() => {{
  const state = {_CHAT_STATE_JS};
  return {{ ready: state?.hasAbortController === true && Boolean({_FIND_STOP_JS}), state }};
}})()"""

# The spy records the page's own cancel requests, the errors it logs and the store at the moment of the click.
_PRESS_STOP_JS = f"""(() => {{
  if (!window.__stopCalls) {{
    window.__stopCalls = [];
    window.__stopConsole = [];
    for (const level of ['error', 'warn']) {{
      const real = console[level].bind(console);
      console[level] = (...args) => {{
        window.__stopConsole.push(level + ': ' + args.map((a) => String(a && a.message ? a.message : a)).join(' ').slice(0, 300));
        real(...args);
      }};
    }}
    const realFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {{
      const url = String(input && input.url ? input.url : input);
      if (!url.includes('/cancel')) return realFetch(input, init);
      const call = {{ url, status: 'pending' }};
      window.__stopCalls.push(call);
      try {{
        const response = await realFetch(input, init);
        call.status = response.status;
        return response;
      }} catch (error) {{
        call.status = String(error);
        throw error;
      }}
    }};
  }}
  const stop = {_FIND_STOP_JS};
  if (!stop) return {{ ready: false }};
  const state = {_CHAT_STATE_JS};
  stop.click();
  return {{ ready: true, state }};
}})()"""

_STOP_REACTION_JS = """(() => ({
  requests: window.__stopCalls ?? 'the spy is gone: the document was replaced',
  toasts: Array.from(document.querySelectorAll('[data-sonner-toast]')).map((toast) => (toast.textContent ?? '').slice(0, 120)),
  console: window.__stopConsole ?? [],
}))()"""


def _reaction(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    reaction = client.evaluate(page, _STOP_REACTION_JS, timeout_sec=15.0)
    assert isinstance(reaction, dict), reaction
    return reaction


def press_stop(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    """Press Stop once the page streams the turn; returns what the page held and did, for the failure message of a Stop that did nothing."""
    appeared = wait_for_state(client, page, _STOP_APPEARED_JS, timeout_sec=_STOP_BUTTON_TIMEOUT_SEC)
    wait_for_state(client, page, _ATTACHED_JS, timeout_sec=_STOP_BUTTON_TIMEOUT_SEC)
    pressed = wait_for_state(client, page, _PRESS_STOP_JS, timeout_sec=_STOP_BUTTON_TIMEOUT_SEC)
    deadline = time.monotonic() + _STOP_REACTION_TIMEOUT_SEC
    reaction = _reaction(client, page)
    while time.monotonic() < deadline and not reaction.get("requests"):
        time.sleep(0.5)
        reaction = _reaction(client, page)
    return {"state_when_stop_appeared": appeared.get("state"), "state_when_pressed": pressed.get("state"), **reaction}
