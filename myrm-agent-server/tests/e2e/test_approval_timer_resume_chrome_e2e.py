"""Chrome LIVE E2E: the runs the server's approval timer continues when nobody presses Approve.

Real business flow, no mocks and no API shortcut for the chat turn itself:

    user sends a message -> live model calls the bash tool -> the run parks behind the approval card
    -> the user leaves the chat and nobody presses Approve -> the server's timer answers as the security setting says (deny or allow)
    -> the timer's run continues the turn without any page -> the user opens the chat again and finds the reply.

An open chat page answers an expired card itself (ToolApprovalExpiryWatcher), so the server's timer would never be the one to act.
The user leaves the chat for a static document of the same origin, which keeps the page bound to the probe's backend.

  - one card, answered by deny and by allow: the reopened chat shows the reply, the server no longer holds the card the timer
    answered, and the timer's run brought the turn's skill hooks back (they fire for the command only when the timer allowed it);
  - two cards in a row, both answered by allow: the run the first timer continues stops at the second card, which gets its own
    timer, and that timer's run finishes the turn: both commands ran, in order, with the skill hooks around each of them.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_approval_timer_resume_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_approval_turn import APPROVAL_PROBE_URL, SHORT_ANSWER, bash_request, run_one_turn
from tests.support.chrome_chat_page_observe import (
    assert_page_settled,
    open_in_fresh_page,
    turn_state,
    wait_for_reply_on_page,
    wait_for_the_stored_reply_watching_the_turn,
    wait_until_parked_at_the_card,
)
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_ui_url
from tests.support.chrome_skill_hooks_approval import wait_for_approval_card
from tests.support.chrome_skill_hooks_live_e2e import SkillChat
from tests.support.e2e_runtime_guard import E2EResourceLedger

# Seconds before the approval timer answers a card nobody answered.
_TIMER_SEC = 45
# Two timers in a row plus the model's turns around them.
_CHAIN_REPLY_TIMEOUT_SEC = 360.0
_FIRST_COMMAND_URL = f"{APPROVAL_PROBE_URL}_FIRST"
_SECOND_COMMAND_URL = f"{APPROVAL_PROBE_URL}_SECOND"
_IDLE_TURN = {"running": False, "awaitingApproval": False}


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
        wait_for_the_stored_reply_watching_the_turn(probe, timeout_sec=_CHAIN_REPLY_TIMEOUT_SEC)
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
