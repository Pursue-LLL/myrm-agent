"""Chrome LIVE E2E: the reply of an approved run appears on the page the user is watching, without a reload.

Real business flow, no mocks and no API shortcut for the chat turn itself:

    user sends a message -> live model calls the bash tool -> the run parks behind the approval card
    -> user presses Approve -> the page sends the resume under the id of the turn that asked
    -> the response to that request is the rest of the turn: the tool runs and the model answers.

A server that answers the resume with the buffered events of the stopped turn leaves the page with a finished-looking turn and no
answer: the run does finish (its reply is stored), and the user sees it only after reloading the chat.

Formal run::

    ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_approval_resume_reply_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_ui_url
from tests.support.chrome_skill_hooks_approval import approve_cards_until_reply, wait_for_approval_card
from tests.support.chrome_skill_hooks_composer import describe_page, drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, audit_hooks, setup_skill_chat
from tests.support.e2e_runtime_guard import E2EResourceLedger

_APPROVAL_PROBE_URL = "http://127.0.0.1:9/APPROVAL_RESUME_REPLY"
# The stored reply is there seconds after the click; the page gets the same time to show it.
_REPLY_ON_PAGE_TIMEOUT_SEC = 60.0

# The answer is a line of its own; the user's message that asks for it is a longer line.
_REPLY_ON_PAGE_JS = (
    f"""(() => (document.body?.innerText ?? '').split('\\n').some((line) => line.trim() === {json.dumps(DONE_TOKEN)}))()"""
)


def _reply_on_page(client: ChromeMcpClient, page: McpPage) -> bool:
    return client.evaluate(page, _REPLY_ON_PAGE_JS, timeout_sec=15.0) is True


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_the_reply_of_an_approved_run_appears_on_the_page_without_a_reload(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "resumereply", audit_hooks, yolo=False)

    def approve_then_watch_the_page(client: ChromeMcpClient, page: McpPage) -> None:
        wait_for_approval_card(client, page)
        assert not _reply_on_page(client, page), "the page already showed the reply while the run was parked behind the approval"
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0)
        deadline = time.monotonic() + _REPLY_ON_PAGE_TIMEOUT_SEC
        while time.monotonic() < deadline:
            if _reply_on_page(client, page):
                return
            time.sleep(1.0)
        pytest.fail(
            f"the reply of the approved run is stored but the page did not show it within {_REPLY_ON_PAGE_TIMEOUT_SEC:.0f}s\n"
            f"{describe_page(client, page)}"
        )

    # One plain command keeps the turn at a single approval card.
    drive_chat_turn(
        get_e2e_ui_url(),
        probe,
        f"Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: "
        f"curl -sS {_APPROVAL_PROBE_URL} . Run no other command. "
        f"After it finishes, whatever its result, reply with exactly: {DONE_TOKEN}",
        while_open=approve_then_watch_the_page,
    )
