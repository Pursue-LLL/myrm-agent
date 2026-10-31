"""The Stop button of the chat page, pressed as a user does, and what the page did about it.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers)

[OUTPUT]
- press_stop(): wait until the chat page attached to a run and offers an enabled Stop, press Stop, and return what the page believed and did (store state when Stop was offered and when it was pressed, cancel requests sent, toasts shown, errors logged)

- finished_fetches(): the page's requests that already ended, with start and duration: whether the stream of a turn the page sent still runs

[POS]
Used by tests/e2e/test_approval_timer_resume_chrome_e2e.py to prove a page attached to a run it did not start can stop that run,
and by tests/e2e/test_chat_stop_button_chrome_e2e.py to prove a page can stop the turn it sent itself.
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
    pageTail: (document.body?.innerText ?? '').slice(-40).replace(/\\s+/g, ' '),
  };
})()"""

# The chat page's own Stop button: the one control that stops a turn the page is attached to, whoever started it. It stays in
# place but disabled while the chat's history loads and no turn is attached.
_FIND_STOP_JS = """Array.from(document.querySelectorAll('button[aria-label]')).find((b) => /^(Stop|停止)$/.test(b.getAttribute('aria-label') ?? '') && !b.disabled)"""

# The page's own requests about the chat's turn, with when they started and how they ended: a page that never asked, or was
# told there was nothing to attach to, shows it here.
_TURN_REQUESTS_JS = """performance.getEntriesByType('resource')
  .filter((entry) => /\\/(attach|turn-state|messages)/.test(entry.name))
  .map((entry) => `${entry.name.replace(/^.*\\/api\\/v1/, '')} @${Math.round(entry.startTime)}ms ${Math.round(entry.duration)}ms ${entry.responseStatus}`)"""

# The bullets of a list answer the page rendered so far: how far the page got with the stream it holds.
_BULLETS_ON_PAGE_JS = "document.querySelectorAll('[data-message-id] li').length"

# Records the page's own cancel requests and the warnings and errors it logs. Installed with the first poll, before the stream the
# page holds can end, so the lines that say why it ended are kept.
_INSTALL_SPIES_JS = """if (!window.__stopCalls) {
    window.__stopCalls = [];
    window.__stopConsole = [];
    for (const level of ['error', 'warn']) {
      const real = console[level].bind(console);
      console[level] = (...args) => {
        window.__stopConsole.push(level + ': ' + args.map((a) => String(a && a.message ? a.message : a)).join(' ').slice(0, 300));
        real(...args);
      };
    }
    const realFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = String(input && input.url ? input.url : input);
      if (!url.includes('/cancel')) return realFetch(input, init);
      const call = { url, status: 'pending' };
      window.__stopCalls.push(call);
      try {
        const response = await realFetch(input, init);
        call.status = response.status;
        call.body = (await response.clone().text()).slice(0, 200);
        return response;
      } catch (error) {
        call.status = String(error);
        throw error;
      }
    };
  }"""


def _stop_appeared_js(*, min_bullets: int, require_controller: bool) -> str:
    """Ready once the page offers an enabled Stop (and, when asked, holds the controller that ends the stream it attached to and shows
    the first bullets of the answer). The trace keeps every change of what the page held while it waited, so a Stop that never came
    up shows when the page stopped streaming."""
    return f"""(() => {{
  {_INSTALL_SPIES_JS}
  const state = {_CHAT_STATE_JS};
  const stop = Boolean({_FIND_STOP_JS});
  const bullets = {_BULLETS_ON_PAGE_JS};
  const held = `loading=${{state?.loading}} controller=${{state?.hasAbortController}} server=${{state?.serverStatus}} stop=${{stop}}`;
  const trace = (window.__stopTrace ??= []);
  if (trace.length === 0 || !trace[trace.length - 1].endsWith(held)) trace.push(`${{Math.round(performance.now())}}ms bullets=${{bullets}} ${{held}}`);
  return {{
    ready: stop && (state?.hasAbortController === true || {str(not require_controller).lower()}) && bullets >= {min_bullets},
    state,
    requests: {_TURN_REQUESTS_JS},
    trace: trace.slice(-30),
    console: window.__stopConsole.slice(-8),
  }};
}})()"""


_PRESS_STOP_JS = f"""(() => {{
  {_INSTALL_SPIES_JS}
  const stop = {_FIND_STOP_JS};
  if (!stop) return {{ ready: false }};
  const state = {_CHAT_STATE_JS};
  stop.click();
  return {{ ready: true, state }};
}})()"""

# Requests that ended, with when they started and how long they lasted: a chat stream listed here has ended, whatever the server does.
_FINISHED_FETCHES_JS = """(() => ({
  nowMs: Math.round(performance.now()),
  fetches: performance.getEntriesByType('resource')
    .filter((entry) => entry.initiatorType === 'fetch' && !/liveness|_rsc=|browser\\/spaces|dev-ports|loop\\/status|push-messages|\\/tasks\\?/.test(entry.name))
    .slice(-14)
    .map((entry) => `${entry.name.replace(/^.*\\/api\\/v1/, '')} @${Math.round(entry.startTime)}ms ${Math.round(entry.duration)}ms ${entry.responseStatus}`),
}))()"""

_STOP_REACTION_JS = """(() => ({
  requests: window.__stopCalls ?? 'the spy is gone: the document was replaced',
  toasts: Array.from(document.querySelectorAll('[data-sonner-toast]')).map((toast) => (toast.textContent ?? '').slice(0, 120)),
  console: window.__stopConsole ?? [],
}))()"""


def _reaction(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    reaction = client.evaluate(page, _STOP_REACTION_JS, timeout_sec=15.0)
    assert isinstance(reaction, dict), reaction
    return reaction


def _request_answered(reaction: dict[str, object]) -> bool:
    requests = reaction.get("requests")
    return (
        isinstance(requests, list)
        and bool(requests)
        and all(isinstance(call, dict) and call.get("status") != "pending" for call in requests)
    )


def finished_fetches(client: ChromeMcpClient, page: McpPage) -> object:
    """The page's own requests that already ended, newest last: a turn stream the page opened is listed here once it ended."""
    return client.evaluate(page, _FINISHED_FETCHES_JS, timeout_sec=15.0)


def press_stop(
    client: ChromeMcpClient, page: McpPage, *, min_bullets: int = 0, require_controller: bool = True
) -> dict[str, object]:
    """Press Stop once the page offers it; returns what the page held and did, for the failure message of a Stop that did nothing.

    A page that attached to a run holds the controller that ends its stream, which proves the attach. A page that sent the turn
    itself may have lost that controller while the server still runs the turn: its Stop then depends on the server's status alone.
    """
    appeared = wait_for_state(
        client,
        page,
        _stop_appeared_js(min_bullets=min_bullets, require_controller=require_controller),
        timeout_sec=_STOP_BUTTON_TIMEOUT_SEC,
    )
    offered_with = appeared.get("state")
    pressed = wait_for_state(client, page, _PRESS_STOP_JS, timeout_sec=_STOP_BUTTON_TIMEOUT_SEC)
    deadline = time.monotonic() + _STOP_REACTION_TIMEOUT_SEC
    reaction = _reaction(client, page)
    while time.monotonic() < deadline and not _request_answered(reaction):
        time.sleep(0.5)
        reaction = _reaction(client, page)
    return {"state_when_stop_was_offered": offered_with, "state_when_pressed": pressed.get("state"), **reaction}
