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
  - while the run is parked and the phone's status board (/mobile/status/<chat id>) is opened on the chat: the board gets the card
    through the same recovery, and Approve there finishes the run (once straight to the backend like every page the harness opens,
    once through the UI server's /api/v1 relay, which is how a browser outside the harness reaches it);
  - while two chats are parked behind their cards: the card of the chat reloaded first does not keep the card of the second
    chat the user opens from coming back, and each card, answered on the page of its own chat, finishes its run;
  - 1.5 s after Approve, while the resumed run writes a long answer;
  - at once after Approve, whether or not the click had reached the server (a card that is still there gets approved again);
  - during the first run of a chat, before any approval, which only has the user's message stored;
  - after the user left the chat and nobody pressed Approve, so the server's approval timer denied the command and ran the rest of
    the turn (an open chat page would answer the expired card itself): the reopened chat shows the reply, and the server no
    longer holds the card the timer answered.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_approval_resume_reply_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.support.chrome_chat_page_observe import (
    assert_board_settled,
    assert_page_settled,
    assert_reply_shown_once,
    assert_run_still_working,
    open_chat_from_sidebar,
    open_in_fresh_page,
    reload_the_chat,
    reply_on_page,
    stored_reply_is_final,
    turn_state,
    wait_for_card_of_open_chat,
    wait_for_mobile_status_board,
    wait_for_reply_on_page,
    wait_for_the_stored_reply_watching_the_turn,
    wait_until_not_streaming,
    wait_until_parked_at_the_card,
)
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_api_url, get_e2e_ui_url
from tests.support.chrome_skill_hooks_approval import approve_cards_until_reply, click_approve, wait_for_approval_card
from tests.support.chrome_skill_hooks_composer import drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat, audit_hooks, setup_skill_chat
from tests.support.e2e_runtime_guard import E2EResourceLedger
from tests.support.hitl_live_e2e import set_private_approval_timeout

_APPROVAL_PROBE_URL = "http://127.0.0.1:9/APPROVAL_RESUME_REPLY"
_RELOAD_AFTER_APPROVE_SEC = 1.5
# Seconds before the approval timer denies a card nobody answered.
_TIMER_SEC = 45
# A long answer keeps the run working well past the few seconds a reload takes, whatever the model's speed.
_LONG_ANSWER_LINES = 600
_SHORT_ANSWER = f"reply with exactly: {DONE_TOKEN}"
_LONG_LIST = (
    f"the integers from 1 to {_LONG_ANSWER_LINES} as a bulleted list, one per bullet, "
    f"and after a blank line end with a last line of exactly: {DONE_TOKEN}"
)


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
    approval_timeout_sec: int | None = None,
) -> None:
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, tag, audit_hooks, yolo=not asks_approval)
    if approval_timeout_sec is not None:
        # The probe's own backend only: the global setting the harness pins on the shared one keeps every other test's card waiting.
        set_private_approval_timeout(get_e2e_api_url(), approval_timeout_sec)
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
        assert not reply_on_page(client, page), "the page already showed the reply while the run was parked behind the approval"
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
        wait_for_reply_on_page(client, page, probe, "the reply of the approved run is stored but the page did not show it")
        reload_the_chat(client, page, chat_url)
        wait_for_reply_on_page(client, page, probe, "after a reload the chat did not show the stored reply of the approved run")

    _run_one_turn(tmp_path, e2e_resource_ledger, "resumereply", _bash_request(_SHORT_ANSWER), approve_then_watch_the_page)


def _reload_and_finish(
    client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str, *, working: bool, asks_approval: bool = True
) -> None:
    reload_the_chat(client, page, chat_url)
    if working:
        assert_run_still_working(probe)
    if asks_approval:
        # A click that never reached the server leaves the card on the reloaded page; the user approves it again.
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
    wait_for_reply_on_page(client, page, probe, "after the reload the chat did not show the reply of the run")
    assert_page_settled(client, page)


def _approve_the_first_card_and_wait_for_the_reply(client: ChromeMcpClient, page: McpPage, probe: SkillChat) -> None:
    """Answer the first card of the dialog, which lists the queued cards of every chat, and let the resumed run end.

    One click, not a loop: the next card in the dialog may belong to another chat, and a resumed run streams into the
    chat that is open, so it has to be answered on its own chat's page.
    """
    click_approve(client, page)
    wait_for_reply_on_page(client, page, probe, "after approving its card the chat did not show the reply of the run")
    wait_until_not_streaming(client, page)
    assert_reply_shown_once(client, page)


def _approve_and_finish(client: ChromeMcpClient, page: McpPage, probe: SkillChat) -> None:
    approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
    wait_for_reply_on_page(
        client, page, probe, "after approving the card that came back the chat did not show the reply of the run"
    )
    assert_page_settled(client, page)


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
        reload_the_chat(client, page, chat_url)
        # The card is not stored with the message: the reloaded page has to get it back from the parked run, and Approve finishes the run.
        wait_for_approval_card(client, page)
        assert not stored_reply_is_final(probe), "the run was not parked behind the card"
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
def test_a_reload_after_the_timeout_answered_the_card_shows_the_reply_and_no_card(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def let_the_timer_answer_then_reload(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_until_parked_at_the_card(probe)
        wait_for_approval_card(client, page)
        # An open chat page answers an expired card itself (ToolApprovalExpiryWatcher), so the server's timer would never be the
        # one to act. The user leaves the chat for a static document of the same origin, which keeps the page bound to the backend.
        client.navigate(page, f"{get_e2e_ui_url().rstrip('/')}/favicon.ico", timeout_ms=30_000)
        # Nobody presses Approve: the timer denies the command and the server runs the rest of the turn without any page.
        wait_for_the_stored_reply_watching_the_turn(probe)
        open_in_fresh_page(client, page, chat_url)
        wait_for_reply_on_page(client, page, probe, "after the timer answered the card the reloaded chat did not show the reply")
        # The card was answered by the timer: the parked run must not hand it to the reloaded page again.
        assert_page_settled(client, page)
        assert turn_state(probe) == {"running": False, "awaitingApproval": False}

    _run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "timeoutcard",
        _bash_request(_SHORT_ANSWER),
        let_the_timer_answer_then_reload,
        approval_timeout_sec=_TIMER_SEC,
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
def test_a_reload_while_the_approved_run_is_still_working_ends_with_its_reply(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def approve_then_reload_mid_run(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_for_approval_card(client, page)
        click_approve(client, page)
        time.sleep(_RELOAD_AFTER_APPROVE_SEC)
        assert not reply_on_page(client, page), "the run had already answered; the reload would not interrupt anything"
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
        assert not reply_on_page(client, page), "the run had already answered; the reload would not interrupt anything"
        _reload_and_finish(client, page, probe, chat_url, working=True, asks_approval=False)

    _run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "reloadfirst",
        f"Use no tool. Write {_LONG_LIST}",
        reload_while_the_first_run_writes,
        asks_approval=False,
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
def test_the_card_of_a_second_parked_chat_comes_back_after_the_first_ones(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    ui_url = get_e2e_ui_url()
    for chat_dir in ("first", "second"):
        (tmp_path / chat_dir).mkdir()
    first = setup_skill_chat(tmp_path / "first", e2e_resource_ledger, "parkedfirst", audit_hooks, yolo=False)
    second = setup_skill_chat(tmp_path / "second", e2e_resource_ledger, "parkedsecond", audit_hooks, yolo=False)
    first_url = f"{ui_url.rstrip('/')}{first.ui_path}"

    def park_and_leave(client: ChromeMcpClient, page: McpPage) -> None:
        wait_for_approval_card(client, page)

    # The second chat parks behind its card and is left: its page closes, its run waits for the user.
    drive_chat_turn(ui_url, second, _bash_request(_SHORT_ANSWER), while_open=park_and_leave)

    def reload_then_open_the_second_chat(client: ChromeMcpClient, page: McpPage) -> None:
        wait_for_approval_card(client, page)
        reload_the_chat(client, page, first_url)
        # The first chat's card is back through the reload recovery and sits in the shared queue ...
        wait_for_card_of_open_chat(client, page, first.chat_id)
        open_chat_from_sidebar(client, page, second.chat_id)
        # ... and must not stop the second chat's card from coming back to join it.
        second_open = wait_for_card_of_open_chat(client, page, second.chat_id)
        assert second_open.get("queuedChats") == [first.chat_id, second.chat_id], second_open
        # The dialog lists both cards in queue order: each is answered on the page of its own chat.
        open_chat_from_sidebar(client, page, first.chat_id)
        wait_for_card_of_open_chat(client, page, first.chat_id)
        _approve_the_first_card_and_wait_for_the_reply(client, page, first)
        open_chat_from_sidebar(client, page, second.chat_id)
        wait_for_card_of_open_chat(client, page, second.chat_id)
        _approve_and_finish(client, page, second)

    drive_chat_turn(ui_url, first, _bash_request(_SHORT_ANSWER), while_open=reload_then_open_the_second_chat)


def _the_board_gets_the_card_and_finishes_the_run(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger, tag: str, *, through_the_ui_relay: bool
) -> None:
    def open_the_board_on_the_parked_chat(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_for_approval_card(client, page)
        # A phone opens the board as a fresh page: nothing of the run is in its stores, and the card is not stored with the chat.
        board_url = f"{get_e2e_ui_url().rstrip('/')}/mobile/status/{probe.chat_id}"
        open_in_fresh_page(client, page, board_url, through_the_ui_relay=through_the_ui_relay)
        wait_for_mobile_status_board(client, page)
        wait_for_card_of_open_chat(client, page, probe.chat_id)
        assert not stored_reply_is_final(probe), "the run was not parked behind the card"
        # The board does not show the reply text: the resumed stream reaching the board's own store is what the click proves.
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
        assert_board_settled(client, page, probe)

    _run_one_turn(tmp_path, e2e_resource_ledger, tag, _bash_request(_SHORT_ANSWER), open_the_board_on_the_parked_chat)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_the_mobile_status_board_of_a_parked_run_gets_the_card_and_finishes_the_run(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    _the_board_gets_the_card_and_finishes_the_run(tmp_path, e2e_resource_ledger, "mobileboard", through_the_ui_relay=False)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_the_board_reached_through_the_ui_relay_gets_the_card_and_finishes_the_run(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    """A phone outside the harness reaches the backend through the UI server's /api/v1 rewrite, which compresses what it may."""
    _the_board_gets_the_card_and_finishes_the_run(tmp_path, e2e_resource_ledger, "relayboard", through_the_ui_relay=True)
