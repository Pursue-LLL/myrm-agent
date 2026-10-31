"""Chrome LIVE E2E: the runs the server's approval timer continues when nobody presses Approve.

Real business flow, no mocks and no API shortcut for the chat turn itself:

    user sends a message -> live model calls the bash tool -> the run parks behind the approval card
    -> the user leaves the chat and nobody presses Approve -> the server's timer answers as the security setting says (deny or allow)
    -> the timer's run continues the turn without any page -> the user opens the chat again and finds the reply.

An open chat page answers an expired card itself (ToolApprovalExpiryWatcher), so the server's timer would never be the one to act.
The user leaves the chat for a static document of the same origin, which keeps the page bound to the probe's backend.

  - one card, answered by deny and by allow: the reopened chat shows the reply, the server no longer holds the card the timer
    answered, and the timer's run brought the turn's skill hooks back (they fire for the command only when the timer allowed it);
  - two cards in a row, both answered by allow: the run the first timer continues stops at the second card, which that run holds
    for the server's turn state while the card's own timer is still running, and that timer's run finishes the turn: both
    commands ran, in order, with the skill hooks around each of them;
  - a reload while the timer's run is still writing: the page attaches to that run and ends with its reply, without a second reload;
  - Stop pressed on a page that attached to the timer's run: the server's run ends, the page stops streaming and the stored turn
    says it was stopped;
  - the next message of the chat after a turn the timer finished runs on the agent thread the timer's run continued (the agent
    loop reports ``continue``), not on a thread rebuilt from the stored chat.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_approval_timer_resume_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.support.chrome_approval_turn import (
    APPROVAL_PROBE_URL,
    LONG_LIST_ANSWER,
    SHORT_ANSWER,
    STOP_LIST_ANSWER,
    bash_request,
    run_one_turn,
)
from tests.support.chrome_chat_page_observe import (
    assert_page_settled,
    assert_run_still_working,
    backend_attach_lines,
    backend_cancel_lines,
    last_completion_status,
    open_chat_from_sidebar,
    open_in_fresh_page,
    reported_history_mode,
    stored_assistant_turns,
    stored_reply_is_final,
    turn_state,
    wait_for_reply_on_page,
    wait_for_the_stored_reply_watching_the_turn,
    wait_until_not_streaming,
    wait_until_parked_at_the_card,
    wait_until_the_turn_ends,
    wait_until_the_turn_runs,
)
from tests.support.chrome_chat_page_stop import attach_console_lines, press_stop
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_api_url, get_e2e_ui_url
from tests.support.chrome_skill_hooks_approval import wait_for_approval_card
from tests.support.chrome_skill_hooks_composer import drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import SkillChat
from tests.support.chrome_skill_hooks_observe import wait_assistant_reply_ending_with
from tests.support.e2e_runtime_guard import E2EResourceLedger

# Seconds before the approval timer answers a card nobody answered.
_TIMER_SEC = 45
# Two timers in a row plus the model's turns around them.
_CHAIN_REPLY_TIMEOUT_SEC = 360.0
_FIRST_COMMAND_URL = f"{APPROVAL_PROBE_URL}_FIRST"
_SECOND_COMMAND_URL = f"{APPROVAL_PROBE_URL}_SECOND"
_IDLE_TURN = {"running": False, "awaitingApproval": False}
_FOLLOW_UP_TOKEN = "TIMER-FOLLOW-UP-OK"


def _recording_hooks(out: Path) -> str:
    """Hooks that append one line per bash call, so a chain of cards leaves one line each (``audit_hooks`` keeps the last only)."""
    return f"""  SessionStart:
    - script: 'printf "%s" "$ARGUMENTS" > {out}/session_payload.json'
      description: Capture the session payload.
  PreToolUse:
    - script: 'printf "%s\\n" "$ARGUMENTS" >> {out}/pre_tool_calls.log'
      tools: [bash_*]
      description: Record each bash call before it runs.
  PostToolUse:
    - script: 'printf "%s\\n" "$ARGUMENTS" >> {out}/post_tool_calls.log'
      tools: [bash_*]
      description: Record each bash call after it ran.
"""


def _two_commands_request(answer: str) -> str:
    return (
        "Run these two plain commands with the bash tool, each in its own bash call and one after the other, never both in one "
        f"call and with no ';', '&&', pipe or redirect. First: curl -sS {_FIRST_COMMAND_URL} . Only after it finished, second: "
        f"curl -sS {_SECOND_COMMAND_URL} . Run no other command. After the second one finishes, whatever its result, {answer}"
    )


def _leave_the_chat_for_a_static_document(client: ChromeMcpClient, page: McpPage) -> None:
    client.navigate(page, f"{get_e2e_ui_url().rstrip('/')}/favicon.ico", timeout_ms=30_000)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.parametrize("behavior", ["deny", "allow"])
def test_a_reload_after_the_timeout_answered_the_card_shows_the_reply_and_no_card(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger, behavior: str
) -> None:
    def let_the_timer_answer_then_reload(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_until_parked_at_the_card(probe)
        wait_for_approval_card(client, page)
        _leave_the_chat_for_a_static_document(client, page)
        # Nobody presses Approve: the timer answers as the security setting says and the server runs the rest of the turn without any page.
        wait_for_the_stored_reply_watching_the_turn(probe)
        open_in_fresh_page(client, page, chat_url)
        wait_for_reply_on_page(client, page, probe, "after the timer answered the card the reloaded chat did not show the reply")
        # The card was answered by the timer: the parked run must not hand it to the reloaded page again.
        assert_page_settled(client, page)
        assert turn_state(probe) == _IDLE_TURN
        # The timer's run is a resume like the page's: it brings the turn's skill hooks back, and the PreToolUse/PostToolUse
        # hooks fire for a command that ran, which the timer's answer decided.
        assert json.loads((probe.out / "session_payload.json").read_text())["is_resume"] is True, (
            "the timer run lost the skill hooks"
        )
        for hook_payload in ("pre_tool_payload.json", "post_tool_payload.json"):
            assert (probe.out / hook_payload).exists() is (behavior == "allow"), f"{hook_payload} with timer behavior {behavior}"

    run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "timeoutcard",
        bash_request(SHORT_ANSWER),
        let_the_timer_answer_then_reload,
        approval_timeout_sec=_TIMER_SEC,
        approval_timeout_behavior=behavior,
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
def test_two_cards_in_a_row_are_answered_by_the_timer_one_after_the_other(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def let_the_timers_answer_both(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_until_parked_at_the_card(probe)
        wait_for_approval_card(client, page)
        _leave_the_chat_for_a_static_document(client, page)
        states = wait_for_the_stored_reply_watching_the_turn(probe, timeout_sec=_CHAIN_REPLY_TIMEOUT_SEC)
        # The run the first timer started stopped at the second card, and nobody answered that card for another timer period: the
        # server held it for that whole time, so a page that reloaded then would have got it back. Seen as a state that awaits
        # approval again after the first card was answered.
        awaiting = [awaiting_approval for _running, awaiting_approval in states]
        assert True in awaiting[awaiting.index(False) :], f"the second card was held by no run: turn states {states}"
        open_in_fresh_page(client, page, chat_url)
        wait_for_reply_on_page(
            client, page, probe, "after the timers answered both cards the reloaded chat did not show the reply"
        )
        assert_page_settled(client, page)
        assert turn_state(probe) == _IDLE_TURN
        before = (probe.out / "pre_tool_calls.log").read_text().splitlines()
        after = (probe.out / "post_tool_calls.log").read_text().splitlines()
        # Two lines each: one bash call per card, in the order the model was told, with the hooks around every one of them.
        assert len(before) == len(after) == 2, f"hook calls: before={before} after={after}"
        assert _FIRST_COMMAND_URL in before[0] and _SECOND_COMMAND_URL in before[1], before
        assert _FIRST_COMMAND_URL in after[0] and _SECOND_COMMAND_URL in after[1], after

    run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "timerchain",
        _two_commands_request(SHORT_ANSWER),
        let_the_timers_answer_both,
        approval_timeout_sec=_TIMER_SEC,
        approval_timeout_behavior="allow",
        hooks_for=_recording_hooks,
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
def test_a_reload_while_the_timer_run_is_still_writing_ends_with_its_reply(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def reload_while_the_timer_run_writes(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_until_parked_at_the_card(probe)
        wait_for_approval_card(client, page)
        _leave_the_chat_for_a_static_document(client, page)
        # The timer answered: the server runs the rest of the turn and the long answer keeps it working while the page comes up.
        wait_until_the_turn_runs(probe)
        open_in_fresh_page(client, page, chat_url)
        assert_run_still_working(probe)
        # The page attached to the run that is writing, so it ends with that run's reply without another reload.
        wait_for_reply_on_page(
            client, page, probe, "the page that reloaded while the timer's run was writing did not end with the run's reply"
        )
        assert_page_settled(client, page)
        assert turn_state(probe) == _IDLE_TURN

    run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "timermid",
        bash_request(LONG_LIST_ANSWER),
        reload_while_the_timer_run_writes,
        approval_timeout_sec=_TIMER_SEC,
        approval_timeout_behavior="allow",
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
def test_stop_pressed_on_a_page_attached_to_the_timer_run_ends_that_run(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def stop_the_run_the_page_attached_to(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_until_parked_at_the_card(probe)
        wait_for_approval_card(client, page)
        # The user waits on the app's start page, which holds no card for the page to answer; the page is loaded long before the
        # timer's run starts, so opening the chat from the sidebar attaches within moments, however slow a cold page load is.
        open_in_fresh_page(client, page, f"{get_e2e_ui_url().rstrip('/')}/")
        wait_until_the_turn_runs(probe)
        run_seen_at = time.monotonic()
        open_chat_from_sidebar(client, page, probe.chat_id)
        assert_run_still_working(probe)
        turn_when_the_page_came_up = turn_state(probe)
        # The page offers Stop because it attached to the run: the run was started by the server's timer, not by this page.
        try:
            page_reaction = press_stop(client, page)
        except AssertionError as error:
            raise AssertionError(
                f"{error}; server turn when the page came up: {turn_when_the_page_came_up}; server turn now: {turn_state(probe)}; "
                f"stored turns: {stored_assistant_turns(probe)}; backend attach lines: {backend_attach_lines(probe)!r}; "
                f"page console about attaching:\n{attach_console_lines(client, page)}"
            ) from error
        print(
            f"E2E_STOP_TIMELINE: seconds from the timer run's start to the pressed Stop: {time.monotonic() - run_seen_at:.1f}",
            flush=True,
        )
        running_when_pressed = turn_state(probe).get("running")
        wait_until_the_turn_ends(probe)
        wait_until_not_streaming(client, page)
        outcome = (
            f"turn running when Stop was pressed: {running_when_pressed}; stored turns: {stored_assistant_turns(probe)}; "
            f"the page's reaction to Stop: {page_reaction}; backend cancel lines: {backend_cancel_lines(probe)!r}"
        )
        assert not stored_reply_is_final(probe), (
            f"the run finished its whole answer although Stop was pressed while it wrote; {outcome}"
        )
        assert last_completion_status(probe) == "cancelled", f"the stored turn is not marked stopped; {outcome}"

    run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "timerstop",
        bash_request(STOP_LIST_ANSWER),
        stop_the_run_the_page_attached_to,
        approval_timeout_sec=_TIMER_SEC,
        approval_timeout_behavior="allow",
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
def test_the_next_message_after_a_timer_finished_the_turn_continues_the_agent_thread(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    def let_the_timer_finish_the_turn(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        wait_until_parked_at_the_card(probe)
        wait_for_approval_card(client, page)
        _leave_the_chat_for_a_static_document(client, page)
        wait_for_the_stored_reply_watching_the_turn(probe)
        assert turn_state(probe) == _IDLE_TURN

    probe = run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "timernext",
        bash_request(SHORT_ANSWER),
        let_the_timer_finish_the_turn,
        approval_timeout_sec=_TIMER_SEC,
        approval_timeout_behavior="allow",
    )
    # The user keeps chatting in the same chat. The thread mirrors the stored chat only if the timer's turn recorded it, which
    # the history mode the agent loop reports for this turn shows: without the record the thread is rebuilt (``replace``).
    drive_chat_turn(get_e2e_ui_url(), probe, f"Reply with exactly: {_FOLLOW_UP_TOKEN}", invoke_skill=False)
    wait_assistant_reply_ending_with(probe.chat_id, get_e2e_api_url(), _FOLLOW_UP_TOKEN, timeout_sec=240.0)
    assert reported_history_mode(probe, _FOLLOW_UP_TOKEN) == "continue"
