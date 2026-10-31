"""The Stop button of the chat page, pressed as a user does, and what the page did about it.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers)

[OUTPUT]
- press_stop(): wait until the chat page attached to a run and offers an enabled Stop, press Stop, and return what the page believed and did (store state when Stop was offered and when it was pressed, cancel requests sent, toasts shown, errors logged)

[POS]
Used by tests/e2e/test_approval_timer_resume_chrome_e2e.py to prove a page attached to a run it did not start can stop that run.
"""

from __future__ import annotations

import time

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, wait_for_state

_STOP_BUTTON_TIMEOUT_SEC = 60.0
# A Stop that reaches the server sends its request within moments; a page that sends nothing stays silent.
_STOP_REACTION_TIMEOUT_SEC = 10.0
_CONSOLE_TAIL_CHARS = 3000

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

# Ready once the page attached to the run: an enabled Stop and the controller that ends the attached stream.
_STOP_APPEARED_JS = f"""(() => {{
  const state = {_CHAT_STATE_JS};
  return {{ ready: Boolean({_FIND_STOP_JS}) && state?.hasAbortController === true, state, requests: {_TURN_REQUESTS_JS} }};
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
        call.body = (await response.clone().text()).slice(0, 200);
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


def _request_answered(reaction: dict[str, object]) -> bool:
    requests = reaction.get("requests")
    return (
        isinstance(requests, list)
        and bool(requests)
        and all(isinstance(call, dict) and call.get("status") != "pending" for call in requests)
    )


def attach_console_lines(client: ChromeMcpClient, page: McpPage) -> str:
    """What the page's chat store logged about attaching to a running turn since the page loaded: why it did or did not attach."""
    try:
        result = client.call_tool(
            "list_console_messages", {"pageId": page.page_id, "types": ["log", "warn", "error"]}, timeout_sec=15.0
        )
    except (RuntimeError, TimeoutError) as error:
        return f"(the page console could not be read: {error})"
    content = result.get("content")
    text = "\n".join(str(item.get("text", "")) for item in content if isinstance(item, dict)) if isinstance(content, list) else ""
    return "\n".join(line for line in text.splitlines() if "ttach" in line or "ATTACH" in line)[-_CONSOLE_TAIL_CHARS:]


def press_stop(client: ChromeMcpClient, page: McpPage) -> dict[str, object]:
    """Press Stop once the page streams the turn; returns what the page held and did, for the failure message of a Stop that did nothing."""
    appeared = wait_for_state(client, page, _STOP_APPEARED_JS, timeout_sec=_STOP_BUTTON_TIMEOUT_SEC)
    offered_with = appeared.get("state")
    pressed = wait_for_state(client, page, _PRESS_STOP_JS, timeout_sec=_STOP_BUTTON_TIMEOUT_SEC)
    deadline = time.monotonic() + _STOP_REACTION_TIMEOUT_SEC
    reaction = _reaction(client, page)
    while time.monotonic() < deadline and not _request_answered(reaction):
        time.sleep(0.5)
        reaction = _reaction(client, page)
    return {"state_when_stop_was_offered": offered_with, "state_when_pressed": pressed.get("state"), **reaction}
