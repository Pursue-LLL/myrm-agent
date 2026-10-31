"""Chrome LIVE E2E: the Stop button of a chat page that sent the turn itself.

Real business flow, no mocks and no API shortcut for the chat turn:

    user types a request that makes the model write a long answer and presses send -> the page offers Stop
    -> the user presses it -> the server's run ends, the page stops streaming and the stored turn says it was stopped.

The page holds the request stream it opened itself (the controller ``sendMessage`` sets), the path every user takes. A page that
attached to a run the server started is the case of ``test_approval_timer_resume_chrome_e2e.py``.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_chat_stop_button_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.support.chrome_approval_turn import STOP_LIST_ANSWER, run_one_turn
from tests.support.chrome_chat_page_observe import (
    backend_cancel_lines,
    last_completion_status,
    stored_assistant_turns,
    stored_reply_is_final,
    turn_state,
    wait_until_not_streaming,
    wait_until_the_turn_ends,
)
from tests.support.chrome_chat_page_stop import finished_fetches, press_stop
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage
from tests.support.chrome_skill_hooks_composer import describe_page
from tests.support.chrome_skill_hooks_live_e2e import SkillChat
from tests.support.e2e_runtime_guard import E2EResourceLedger

# A turn stopped before the model wrote anything stores no assistant turn (the session is committed with the first output);
# the Stop of this test lands once a few bullets of the answer are on screen.
_BULLETS_BEFORE_STOP = 5


def _wait_for_a_stored_assistant_turn(probe: SkillChat, *, timeout_sec: float = 30.0) -> None:
    """The turn is stored after the server reports no run any more; a missing row after the wait is the finding."""
    deadline = time.monotonic() + timeout_sec
    while not stored_assistant_turns(probe):
        assert time.monotonic() < deadline, (
            f"no assistant turn stored {timeout_sec:.0f}s after the run ended; backend cancel lines: {backend_cancel_lines(probe)!r}"
        )
        time.sleep(1.0)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_stop_pressed_on_a_turn_the_page_sent_ends_that_turn(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    def stop_the_turn_the_page_sent(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        turn_when_sent = turn_state(probe)
        try:
            page_reaction = press_stop(client, page, min_bullets=_BULLETS_BEFORE_STOP, require_controller=False)
        except AssertionError as error:
            raise AssertionError(
                f"{error}; server turn when the message was stored: {turn_when_sent}; server turn now: "
                f"{turn_state(probe)}; stored turns: {stored_assistant_turns(probe)}; {describe_page(client, page)}; "
                f"page requests that ended: {finished_fetches(client, page)}"
            ) from error
        wait_until_the_turn_ends(probe)
        wait_until_not_streaming(client, page)
        _wait_for_a_stored_assistant_turn(probe)
        outcome = (
            f"server turn when the message was stored: {turn_when_sent}; stored turns: {stored_assistant_turns(probe)}; "
            f"the page's reaction to Stop: {page_reaction}; backend cancel lines: {backend_cancel_lines(probe)!r}"
        )
        assert not stored_reply_is_final(probe), f"the run finished its whole answer although Stop was pressed; {outcome}"
        assert last_completion_status(probe) == "cancelled", f"the stored turn is not marked stopped; {outcome}"

    run_one_turn(
        tmp_path,
        e2e_resource_ledger,
        "pagestop",
        f"Use no tool. {STOP_LIST_ANSWER}",
        stop_the_turn_the_page_sent,
        asks_approval=False,
    )
