"""Chrome LIVE E2E: the reply of an approved run appears on the page the user is watching, and is still there after a reload.

Real business flow, no mocks and no API shortcut for the chat turn itself:

    user sends a message -> live model calls the bash tool -> the run parks behind the approval card
    -> user presses Approve -> the page sends the resume under the id of the turn that asked
    -> the response to that request is the rest of the turn: the tool runs and the model answers
    -> the user reloads the chat and the stored reply is there.

A server that answers the resume with the buffered events of the stopped turn leaves the page with a finished-looking turn and no
answer: the run does finish (its reply is stored), and the user sees it only after reloading the chat.

The reload tests reload the page in the middle of a run, and the reloaded chat must pick the run up and end with its reply:
  - while the run is parked behind the approval card: the card comes back, and Approve finishes the run;
  - 1.5 s after Approve, while the resumed run writes a long answer;
  - at once after Approve, whether or not the click had reached the server (a card that is still there gets approved again);
  - during the first run of a chat, before any approval, which only has the user's message stored.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_approval_resume_reply_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    get_e2e_api_url,
    get_e2e_ui_url,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_approval import approve_cards_until_reply, click_approve, wait_for_approval_card
from tests.support.chrome_skill_hooks_composer import describe_page, drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat, audit_hooks, setup_skill_chat
from tests.support.chrome_skill_hooks_observe import completed_assistant_replies, completed_reply_containing, stored_messages
from tests.support.e2e_runtime_guard import E2EResourceLedger

_APPROVAL_PROBE_URL = "http://127.0.0.1:9/APPROVAL_RESUME_REPLY"
# The stored reply is there seconds after the click; the page gets the same time to show it, live and after a reload.
_REPLY_ON_PAGE_TIMEOUT_SEC = 60.0
_RELOAD_TIMEOUT_MS = 90_000
_RELOAD_AFTER_APPROVE_SEC = 1.5
_SETTLED_TIMEOUT_SEC = 60.0
# A long answer keeps the run working well past the few seconds a reload takes, whatever the model's speed.
_LONG_ANSWER_LINES = 600
_SHORT_ANSWER = f"reply with exactly: {DONE_TOKEN}"
_LONG_LIST = (
    f"the integers from 1 to {_LONG_ANSWER_LINES} as a bulleted list, one per bullet, "
    f"and after a blank line end with a last line of exactly: {DONE_TOKEN}"
)

# A flag on the window lives exactly as long as the document: it proves the reload replaced the page the reply was streamed to.
_MARK_DOCUMENT_JS = "(() => { window.__MYRM_E2E_BEFORE_RELOAD__ = true; return true; })()"
_DOCUMENT_IS_MARKED_JS = "window.__MYRM_E2E_BEFORE_RELOAD__ === true"

# The answer is a line of its own; the user's message that asks for it is a longer line.
_REPLY_ON_PAGE_JS = (
    f"""(() => (document.body?.innerText ?? '').split('\\n').some((line) => line.trim() === {json.dumps(DONE_TOKEN)}))()"""
)

# The page has stopped streaming and holds no approval card: the user can send the next message.
_SETTLED_JS = """(() => {
  const chat = window.__MYRM_E2E_CHAT__;
  const turn = chat?.turnSnapshot?.() ?? {};
  const queueLen = Number(chat?.toolApprovalSnapshot?.().queueLen ?? 0);
  return { ready: turn.isStreaming === false && queueLen === 0, isStreaming: turn.isStreaming ?? null, queueLen };
})()"""

_FAILURE_TAIL_CHARS = 300
_PAGE_TEXT_TAIL_JS = f"(() => (document.body?.innerText ?? '').slice(-{_FAILURE_TAIL_CHARS}))()"

_REPLY_LINE_COUNT_JS = f"""(() => (document.body?.innerText ?? '').split('\\n').filter((line) => line.trim() === {json.dumps(DONE_TOKEN)}).length)()"""


def _reply_on_page(client: ChromeMcpClient, page: McpPage) -> bool:
    return client.evaluate(page, _REPLY_ON_PAGE_JS, timeout_sec=15.0) is True


def _stored_reply_is_final(probe: SkillChat) -> bool:
    return completed_reply_containing(stored_messages(probe.chat_id, get_e2e_api_url()), DONE_TOKEN) is not None


def _assert_run_still_working(probe: SkillChat) -> None:
    """The reloaded page came up while the run was still writing: otherwise the reload met no running turn and proves nothing."""
    assert not _stored_reply_is_final(probe), "the run had finished before the reloaded page came up"


def _assert_page_settled(client: ChromeMcpClient, page: McpPage) -> None:
    """The reply is on the page and the turn is over for it: not streaming, no approval card, the reply shown once."""
    wait_for_state(client, page, _SETTLED_JS, timeout_sec=_SETTLED_TIMEOUT_SEC)
    shown = client.evaluate(page, _REPLY_LINE_COUNT_JS, timeout_sec=15.0)
    assert shown == 1, f"the reply is shown {shown} times on the reloaded page"


def _stored_reply_tail(probe: SkillChat) -> str:
    replies = completed_assistant_replies(stored_messages(probe.chat_id, get_e2e_api_url()))
    return replies[-1][-_FAILURE_TAIL_CHARS:] if replies else "(no completed assistant reply stored)"


def _wait_for_reply_on_page(client: ChromeMcpClient, page: McpPage, probe: SkillChat, failure: str) -> None:
    deadline = time.monotonic() + _REPLY_ON_PAGE_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if _reply_on_page(client, page):
            return
        time.sleep(1.0)
    page_tail = client.evaluate(page, _PAGE_TEXT_TAIL_JS, timeout_sec=15.0)
    pytest.fail(
        f"{failure} within {_REPLY_ON_PAGE_TIMEOUT_SEC:.0f}s\n{describe_page(client, page)}\n"
        f"page text ends with: {page_tail!r}\nstored reply ends with: {_stored_reply_tail(probe)!r}"
    )


def _reload_the_chat(client: ChromeMcpClient, page: McpPage, chat_url: str) -> None:
    assert client.evaluate(page, _MARK_DOCUMENT_JS, timeout_sec=15.0) is True
    reload_mcp_page(client, page, target_url=chat_url, timeout_ms=_RELOAD_TIMEOUT_MS)
    wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
    assert client.evaluate(page, _DOCUMENT_IS_MARKED_JS, timeout_sec=15.0) is False, "the page was not reloaded"


def _bash_request(answer: str) -> str:
    # One plain command keeps the turn at a single approval card.
    return (
        f"Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: "
        f"curl -sS {_APPROVAL_PROBE_URL} . Run no other command. After it finishes, whatever its result, {answer}"
    )


def _run_one_turn(
    tmp_path: Path,
    e2e_resource_ledger: E2EResourceLedger,
    tag: str,
    request: str,
    watch: Callable[[ChromeMcpClient, McpPage, SkillChat, str], None],
    *,
    asks_approval: bool = True,
) -> None:
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, tag, audit_hooks, yolo=not asks_approval)
    chat_url = f"{get_e2e_ui_url().rstrip('/')}{probe.ui_path}"
    drive_chat_turn(
        get_e2e_ui_url(),
        probe,
        request,
        invoke_skill=asks_approval,
        while_open=lambda client, page: watch(client, page, probe, chat_url),
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_the_reply_of_an_approved_run_shows_live_and_stays_after_a_reload(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def approve_then_watch_the_page(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_for_approval_card(client, page)
        assert not _reply_on_page(client, page), "the page already showed the reply while the run was parked behind the approval"
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
        _wait_for_reply_on_page(client, page, probe, "the reply of the approved run is stored but the page did not show it")
        _reload_the_chat(client, page, chat_url)
        _wait_for_reply_on_page(client, page, probe, "after a reload the chat did not show the stored reply of the approved run")

    _run_one_turn(tmp_path, e2e_resource_ledger, "resumereply", _bash_request(_SHORT_ANSWER), approve_then_watch_the_page)


def _reload_and_finish(
    client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str, *, working: bool, asks_approval: bool = True
) -> None:
    _reload_the_chat(client, page, chat_url)
    if working:
        _assert_run_still_working(probe)
    if asks_approval:
        # A click that never reached the server leaves the card on the reloaded page; the user approves it again.
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
    _wait_for_reply_on_page(client, page, probe, "after the reload the chat did not show the reply of the run")
    _assert_page_settled(client, page)


def _approve_and_finish(client: ChromeMcpClient, page: McpPage, probe: SkillChat) -> None:
    approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
    _wait_for_reply_on_page(
        client, page, probe, "after approving the card that came back the chat did not show the reply of the run"
    )
    _assert_page_settled(client, page)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_reload_while_the_run_waits_for_approval_brings_the_card_back(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def reload_behind_the_card(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_for_approval_card(client, page)
        _reload_the_chat(client, page, chat_url)
        # The card is not stored with the message: the reloaded page has to get it back from the parked run, and Approve finishes the run.
        wait_for_approval_card(client, page)
        assert not _stored_reply_is_final(probe), "the run was not parked behind the card"
        _approve_and_finish(client, page, probe)

    _run_one_turn(tmp_path, e2e_resource_ledger, "reloadcard", _bash_request(_SHORT_ANSWER), reload_behind_the_card)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_reload_while_the_approved_run_is_still_working_ends_with_its_reply(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def approve_then_reload_mid_run(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_for_approval_card(client, page)
        click_approve(client, page)
        time.sleep(_RELOAD_AFTER_APPROVE_SEC)
        assert not _reply_on_page(client, page), "the run had already answered; the reload would not interrupt anything"
        _reload_and_finish(client, page, probe, chat_url, working=True)

    _run_one_turn(tmp_path, e2e_resource_ledger, "reloadmid", _bash_request(f"write {_LONG_LIST}"), approve_then_reload_mid_run)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_reload_right_after_pressing_approve_ends_with_the_reply(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def approve_then_reload_at_once(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_for_approval_card(client, page)
        click_approve(client, page)
        # Whether the resume request left the page before it went away is up to the browser: both outcomes must end the same way.
        _reload_and_finish(client, page, probe, chat_url, working=False)

    _run_one_turn(tmp_path, e2e_resource_ledger, "reloadnow", _bash_request(f"write {_LONG_LIST}"), approve_then_reload_at_once)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_reload_while_the_first_run_is_still_writing_ends_with_its_reply(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def reload_while_the_first_run_writes(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        # Only the user's message is stored while the first run writes: the reloaded page has no reply to show but its own.
        assert not _reply_on_page(client, page), "the run had already answered; the reload would not interrupt anything"
        _reload_and_finish(client, page, probe, chat_url, working=True, asks_approval=False)

    _run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "reloadfirst",
        f"Use no tool. Write {_LONG_LIST}",
        reload_while_the_first_run_writes,
        asks_approval=False,
    )
