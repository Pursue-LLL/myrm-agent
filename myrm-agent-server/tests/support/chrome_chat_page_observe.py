"""What a user sees on the chat page after a run was parked behind an approval card, and how the page is reloaded or switched.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers, reload)
- tests.support.chrome_skill_hooks_composer (POS: the page's own account of a turn)
- tests.support.chrome_skill_hooks_live_e2e (POS: SkillChat probe, DONE_TOKEN)
- tests.support.chrome_skill_hooks_observe (POS: stored chat)

[OUTPUT]
- reply_on_page() / wait_for_reply_on_page(): the reply is a line of the transcript (the sidebar's previews do not count)
- assert_reply_shown_once() / assert_page_settled(): reply shown once; settled adds not streaming and no approval card
- assert_board_settled(): the phone's board shows progress, not the reply: not streaming, no approval card, the stored reply is final
- reload_the_chat() / open_in_fresh_page() / open_chat_from_sidebar(): reload the document, visit another page afresh (directly or through the UI server's relay), or switch chats inside the running page
- wait_for_card_of_open_chat(): the open chat's own card is in the shared approval queue and on screen
- wait_for_mobile_status_board(): the phone's status board is the page on screen
- wait_until_not_streaming() / stored_reply_is_final() / assert_run_still_working()
- turn_state() / wait_until_parked_at_the_card() / wait_for_the_stored_reply_watching_the_turn(): what the server holds of the chat's turn (running, parked behind a card), read from /agents/chat/<id>/turn-state

[POS]
Shared by tests/e2e/test_approval_resume_reply_chrome_e2e.py and test_approval_timer_resume_chrome_e2e.py; the scenarios stay there, the page-side probes live here.
"""

from __future__ import annotations

import json
import re
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    http_json,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_composer import describe_page
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat
from tests.support.chrome_skill_hooks_observe import (
    backend_log_since,
    completed_assistant_replies,
    completed_reply_containing,
    stored_messages,
)

# The stored reply is there seconds after the click; the page gets the same time to show it, live and after a reload.
_REPLY_ON_PAGE_TIMEOUT_SEC = 60.0
_RELOAD_TIMEOUT_MS = 90_000
_SETTLED_TIMEOUT_SEC = 60.0
_CARD_ON_PAGE_TIMEOUT_SEC = 60.0

# A flag on the window lives exactly as long as the document: it proves the reload replaced the page the reply was streamed to.
_MARK_DOCUMENT_JS = "(() => { window.__MYRM_E2E_BEFORE_RELOAD__ = true; return true; })()"
_DOCUMENT_IS_MARKED_JS = "window.__MYRM_E2E_BEFORE_RELOAD__ === true"
# The page talks to the backend directly only while it carries the runtime binding the harness injected; without it every
# request goes through the UI server's /api/v1 relay.
_PAGE_IS_BOUND_JS = """Boolean(window.__MYRM_E2E_RUNTIME__?.apiBase ?? window.__MYRM_E2E_API_BASE__)
  || String(window.name).startsWith('myrm-e2e-v1:')"""

# The answer is a line of its own; the user's message that asks for it is a longer line. The sidebar previews the last
# message of every chat, so only the lines outside it belong to the transcript.
_REPLY_LINE_COUNT_JS = f"""(() => {{
  const count = (text) => text.split('\\n').filter((line) => line.trim() === {json.dumps(DONE_TOKEN)}).length;
  const sidebar = Array.from(document.querySelectorAll('aside')).reduce((sum, el) => sum + count(el.innerText ?? ''), 0);
  return count(document.body?.innerText ?? '') - sidebar;
}})()"""
_REPLY_ON_PAGE_JS = f"({_REPLY_LINE_COUNT_JS}) > 0"

# Where the reply is on the page and what the chat store holds, for a reply that is not shown exactly once.
_REPLY_PLACES_JS = f"""(() => {{
  const chat = window.__myrmChatStore?.getState();
  const rows = (chat?.messages ?? []).map((m) => ({{
    role: m.role,
    id: String(m.messageId).slice(0, 14),
    requestId: m.requestMessageId ? String(m.requestMessageId).slice(0, 14) : null,
    status: m.completionStatus ?? null,
    length: typeof m.content === 'string' ? m.content.length : null,
    tail: typeof m.content === 'string' ? m.content.slice(-40) : null,
  }}));
  const bodyText = document.body?.innerText ?? '';
  const holders = Array.from(document.querySelectorAll('*'))
    .filter((el) => el.children.length === 0 && (el.textContent ?? '').trim() === {json.dumps(DONE_TOKEN)})
    .map((el) => {{
      const path = [];
      for (let node = el; node && path.length < 6; node = node.parentElement) path.push(node.tagName.toLowerCase());
      return path.join('<');
    }});
  return {{
    chatId: chat?.chatId,
    rows,
    holders,
    innerTextLines: bodyText.split('\\n').filter((line) => line.trim() === {json.dumps(DONE_TOKEN)}).length,
    textContentHasToken: (document.body?.textContent ?? '').includes({json.dumps(DONE_TOKEN)}),
  }};
}})()"""

# The page has stopped streaming and holds no approval card: the user can send the next message.
_SETTLED_JS = """(() => {
  const chat = window.__MYRM_E2E_CHAT__;
  const turn = chat?.turnSnapshot?.() ?? {};
  const queueLen = Number(chat?.toolApprovalSnapshot?.().queueLen ?? 0);
  return { ready: turn.isStreaming === false && queueLen === 0, isStreaming: turn.isStreaming ?? null, queueLen };
})()"""


def _card_of_open_chat_js(chat_id: str) -> str:
    return f"""(() => {{
  const chat = window.__myrmChatStore?.getState();
  const queuedChats = window.__MYRM_E2E_CHAT__?.toolApprovalSnapshot?.().chatIds ?? [];
  const hasApprove = Array.from(document.querySelectorAll('button')).some((btn) => /Approve|批准/.test((btn.textContent || '').trim()));
  const open = chat?.chatId === {json.dumps(chat_id)} && chat?.isMessagesLoaded === true;
  return {{ ready: open && hasApprove && queuedChats.includes({json.dumps(chat_id)}), open, hasApprove, queuedChats }};
}})()"""


# The approval cards of all chats share one queue: the open chat's own card is the one queued under its id.
def wait_for_card_of_open_chat(client: ChromeMcpClient, page: McpPage, chat_id: str) -> dict[str, object]:
    """Block until `chat_id` is the open chat and an approval card of it is on screen; returns the queued chats' ids."""
    return wait_for_state(client, page, _card_of_open_chat_js(chat_id), timeout_sec=_CARD_ON_PAGE_TIMEOUT_SEC)


# The phone's status board, not the desktop chat page: its header carries this link and its route is /mobile/status/<chat id>.
_MOBILE_BOARD_OPEN_JS = """(() => ({
  ready: location.pathname.startsWith('/mobile/status/')
    && document.querySelector('[data-testid="mobile-command-view-full-conversation"]') !== null,
  path: location.pathname,
}))()"""


def wait_for_mobile_status_board(client: ChromeMcpClient, page: McpPage) -> None:
    """Block until the mobile status board is the page on screen."""
    wait_for_state(client, page, _MOBILE_BOARD_OPEN_JS, timeout_sec=_CARD_ON_PAGE_TIMEOUT_SEC)


def wait_until_not_streaming(client: ChromeMcpClient, page: McpPage) -> None:
    """The page's turn is over; cards of other chats may still wait in the queue."""
    wait_for_state(client, page, _NOT_STREAMING_JS, timeout_sec=_SETTLED_TIMEOUT_SEC)


def _sidebar_row_js(chat_id: str, *, click: bool) -> str:
    return f"""(() => {{
  const row = document.querySelector('a[href="/{chat_id}"]');
  if (!row) return {{ ready: false, rows: Array.from(document.querySelectorAll('a[href]')).slice(0, 8).map((a) => a.getAttribute('href')) }};
  if ({json.dumps(click)}) row.click();
  return {{ ready: true }};
}})()"""


_NOT_STREAMING_JS = """(() => {
  const isStreaming = window.__MYRM_E2E_CHAT__?.turnSnapshot?.().isStreaming ?? null;
  return { ready: isStreaming === false, isStreaming };
})()"""

_FAILURE_TAIL_CHARS = 300
_PAGE_TEXT_TAIL_JS = f"(() => (document.body?.innerText ?? '').slice(-{_FAILURE_TAIL_CHARS}))()"


def reply_on_page(client: ChromeMcpClient, page: McpPage) -> bool:
    return client.evaluate(page, _REPLY_ON_PAGE_JS, timeout_sec=15.0) is True


def stored_reply_is_final(probe: SkillChat) -> bool:
    return completed_reply_containing(stored_messages(probe.chat_id, get_e2e_api_url()), DONE_TOKEN) is not None


def assert_run_still_working(probe: SkillChat) -> None:
    """The reloaded page came up while the run was still writing: otherwise the reload met no running turn and proves nothing."""
    assert not stored_reply_is_final(probe), "the run had finished before the reloaded page came up"


def turn_state(probe: SkillChat) -> dict[str, object]:
    reply = http_json("GET", f"{get_e2e_api_url()}/api/v1/agents/chat/{probe.chat_id}/turn-state")
    data = reply.get("data") if isinstance(reply, dict) else None
    assert isinstance(data, dict), reply
    return data


def wait_until_parked_at_the_card(probe: SkillChat, *, timeout_sec: float = 120.0) -> None:
    """The server holds the run at its approval card: without this the later steps could pass for a run that never asked."""
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = turn_state(probe)
        if last.get("awaitingApproval") is True:
            return
        time.sleep(0.25)
    log = backend_log_since(get_e2e_api_url(), probe.log_offset, limit=100_000)
    relevant = [line for line in log.splitlines() if re.search(r"approv|guardrail|permission|blocked|HITL|denied", line, re.I)]
    stored = [
        f"{m.get('role')}: {str(m.get('content') or m.get('message') or '')[:240]!r}"
        for m in stored_messages(probe.chat_id, get_e2e_api_url())
    ]
    pytest.fail(
        f"the run never parked at an approval card within {timeout_sec:.0f}s; last turn-state: {last}\n"
        f"stored messages: {stored}\nbackend log lines about approvals:\n" + "\n".join(relevant[-40:])
    )


def wait_for_the_stored_reply_watching_the_turn(probe: SkillChat, *, timeout_sec: float = 240.0) -> None:
    """Wait for the reply the run stores without any click, printing how the server's view of the turn changed meanwhile."""
    started = time.monotonic()
    timeline: list[str] = []
    last: tuple[object, object] | None = None
    while time.monotonic() - started < timeout_sec:
        state = turn_state(probe)
        seen = (state.get("running"), state.get("awaitingApproval"))
        if seen != last:
            timeline.append(f"{time.monotonic() - started:.0f}s running={seen[0]} awaitingApproval={seen[1]}")
            last = seen
        if stored_reply_is_final(probe):
            print(f"E2E_TURN_STATE_TIMELINE: {timeline}", flush=True)
            return
        time.sleep(1.0)
    pytest.fail(f"no stored reply within {timeout_sec:.0f}s; turn-state timeline: {timeline}")


def assert_reply_shown_once(client: ChromeMcpClient, page: McpPage) -> None:
    """The transcript holds the reply once: a run streamed into the wrong chat or merged with its stored row shows twice."""
    shown = client.evaluate(page, _REPLY_LINE_COUNT_JS, timeout_sec=15.0)
    if shown != 1:
        places = client.evaluate(page, _REPLY_PLACES_JS, timeout_sec=15.0)
        pytest.fail(f"the reply is shown {shown} times on the page: {json.dumps(places, ensure_ascii=False)}")


def assert_board_settled(client: ChromeMcpClient, page: McpPage, probe: SkillChat) -> None:
    """The run ended and the board holds no card. The board shows progress, not the reply, so the stored reply is the proof."""
    wait_for_state(client, page, _SETTLED_JS, timeout_sec=_SETTLED_TIMEOUT_SEC)
    assert stored_reply_is_final(probe), "the board settled but the run has no completed reply"


def assert_page_settled(client: ChromeMcpClient, page: McpPage) -> None:
    """The reply is on the page and the turn is over for it: not streaming, no approval card, the reply shown once."""
    wait_for_state(client, page, _SETTLED_JS, timeout_sec=_SETTLED_TIMEOUT_SEC)
    assert_reply_shown_once(client, page)


def _stored_reply_tail(probe: SkillChat) -> str:
    replies = completed_assistant_replies(stored_messages(probe.chat_id, get_e2e_api_url()))
    return replies[-1][-_FAILURE_TAIL_CHARS:] if replies else "(no completed assistant reply stored)"


def wait_for_reply_on_page(client: ChromeMcpClient, page: McpPage, probe: SkillChat, failure: str) -> None:
    deadline = time.monotonic() + _REPLY_ON_PAGE_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if reply_on_page(client, page):
            return
        time.sleep(1.0)
    page_tail = client.evaluate(page, _PAGE_TEXT_TAIL_JS, timeout_sec=15.0)
    places = client.evaluate(page, _REPLY_PLACES_JS, timeout_sec=15.0)
    pytest.fail(
        f"{failure} within {_REPLY_ON_PAGE_TIMEOUT_SEC:.0f}s\n{describe_page(client, page)}\n"
        f"store rows and elements that hold the reply: {json.dumps(places, ensure_ascii=False)}\n"
        f"page text ends with: {page_tail!r}\nstored reply ends with: {_stored_reply_tail(probe)!r}"
    )


def open_chat_from_sidebar(client: ChromeMcpClient, page: McpPage, chat_id: str) -> None:
    """Switch chats the way a user does, inside the running page: the stores keep what they hold."""
    wait_for_state(client, page, _sidebar_row_js(chat_id, click=False), timeout_sec=60.0)
    clicked = client.evaluate(page, _sidebar_row_js(chat_id, click=True), timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked


def _replace_document(client: ChromeMcpClient, page: McpPage, url: str, *, navigate: bool, bound: bool = True) -> None:
    assert client.evaluate(page, _MARK_DOCUMENT_JS, timeout_sec=15.0) is True
    if not bound:
        # Going through about:blank drops the binding that lives in window.name: the page reaches the backend through the
        # UI server's /api/v1 relay, as a browser outside the harness does.
        reload_mcp_page(client, page, target_url=url, ignore_cache=True, timeout_ms=_RELOAD_TIMEOUT_MS)
    elif navigate:
        # A direct same-origin navigation keeps the binding, so the page talks to the backend directly.
        client.navigate(page, url, timeout_ms=_RELOAD_TIMEOUT_MS)
    else:
        reload_mcp_page(client, page, target_url=url, timeout_ms=_RELOAD_TIMEOUT_MS)
    wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=url)
    assert client.evaluate(page, _DOCUMENT_IS_MARKED_JS, timeout_sec=15.0) is False, "the page was not replaced"
    is_bound = client.evaluate(page, _PAGE_IS_BOUND_JS, timeout_sec=15.0)
    assert is_bound is bound, (
        f"the page is {'' if is_bound else 'not '}bound to the backend, expected {'bound' if bound else 'unbound'}"
    )


def reload_the_chat(client: ChromeMcpClient, page: McpPage, chat_url: str) -> None:
    """Reload the open chat page."""
    _replace_document(client, page, chat_url, navigate=False)


def open_in_fresh_page(client: ChromeMcpClient, page: McpPage, page_url: str, *, through_the_ui_relay: bool = False) -> None:
    """Visit ``page_url`` as a freshly loaded page: nothing of the page that was open is left in the stores.

    The page talks to the backend directly, like every page the harness opens. With ``through_the_ui_relay`` it reaches the
    same backend the way a browser outside the harness does, through the UI server's ``/api/v1`` rewrite.
    """
    _replace_document(client, page, page_url, navigate=True, bound=not through_the_ui_relay)
