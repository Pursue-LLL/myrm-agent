"""What a user sees on the chat page after a run was parked behind an approval card, and how the page is reloaded or switched.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: CDP page helpers, reload)
- tests.support.chrome_skill_hooks_composer (POS: the page's own account of a turn)
- tests.support.chrome_skill_hooks_live_e2e (POS: SkillChat probe, DONE_TOKEN)
- tests.support.chrome_skill_hooks_observe (POS: stored chat)

[OUTPUT]
- reply_on_page() / wait_for_reply_on_page(): the reply is a line of the transcript (the sidebar's previews do not count)
- assert_reply_shown_once() / assert_page_settled(): reply shown once; settled adds not streaming and no approval card
- reload_the_chat() / open_chat_from_sidebar(): reload the document, or switch chats inside the running page
- wait_for_card_of_open_chat(): the open chat's own card is in the shared approval queue and on screen
- wait_until_not_streaming() / stored_reply_is_final() / assert_run_still_working()

[POS]
Shared by tests/e2e/test_approval_resume_reply_chrome_e2e.py; the scenarios stay there, the page-side probes live here.
"""

from __future__ import annotations

import json
import time

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_composer import describe_page
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat
from tests.support.chrome_skill_hooks_observe import completed_assistant_replies, completed_reply_containing, stored_messages

# The stored reply is there seconds after the click; the page gets the same time to show it, live and after a reload.
_REPLY_ON_PAGE_TIMEOUT_SEC = 60.0
_RELOAD_TIMEOUT_MS = 90_000
_SETTLED_TIMEOUT_SEC = 60.0
_CARD_ON_PAGE_TIMEOUT_SEC = 60.0

# A flag on the window lives exactly as long as the document: it proves the reload replaced the page the reply was streamed to.
_MARK_DOCUMENT_JS = "(() => { window.__MYRM_E2E_BEFORE_RELOAD__ = true; return true; })()"
_DOCUMENT_IS_MARKED_JS = "window.__MYRM_E2E_BEFORE_RELOAD__ === true"

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
    status: m.completionStatus ?? null,
    tail: typeof m.content === 'string' ? m.content.slice(-40) : null,
  }}));
  const holders = Array.from(document.querySelectorAll('*'))
    .filter((el) => el.children.length === 0 && (el.textContent ?? '').trim() === {json.dumps(DONE_TOKEN)})
    .map((el) => {{
      const path = [];
      for (let node = el; node && path.length < 6; node = node.parentElement) path.push(node.tagName.toLowerCase());
      return path.join('<');
    }});
  return {{ chatId: chat?.chatId, rows, holders }};
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


def assert_reply_shown_once(client: ChromeMcpClient, page: McpPage) -> None:
    """The transcript holds the reply once: a run streamed into the wrong chat or merged with its stored row shows twice."""
    shown = client.evaluate(page, _REPLY_LINE_COUNT_JS, timeout_sec=15.0)
    if shown != 1:
        places = client.evaluate(page, _REPLY_PLACES_JS, timeout_sec=15.0)
        pytest.fail(f"the reply is shown {shown} times on the page: {json.dumps(places, ensure_ascii=False)}")


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
    pytest.fail(
        f"{failure} within {_REPLY_ON_PAGE_TIMEOUT_SEC:.0f}s\n{describe_page(client, page)}\n"
        f"page text ends with: {page_tail!r}\nstored reply ends with: {_stored_reply_tail(probe)!r}"
    )


def open_chat_from_sidebar(client: ChromeMcpClient, page: McpPage, chat_id: str) -> None:
    """Switch chats the way a user does, inside the running page: the stores keep what they hold."""
    wait_for_state(client, page, _sidebar_row_js(chat_id, click=False), timeout_sec=60.0)
    clicked = client.evaluate(page, _sidebar_row_js(chat_id, click=True), timeout_sec=15.0)
    assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked


def reload_the_chat(client: ChromeMcpClient, page: McpPage, chat_url: str) -> None:
    assert client.evaluate(page, _MARK_DOCUMENT_JS, timeout_sec=15.0) is True
    reload_mcp_page(client, page, target_url=chat_url, timeout_ms=_RELOAD_TIMEOUT_MS)
    wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
    assert client.evaluate(page, _DOCUMENT_IS_MARKED_JS, timeout_sec=15.0) is False, "the page was not reloaded"
