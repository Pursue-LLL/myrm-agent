"""One live-model turn of the approval-card Chrome E2E scenarios: the skill chat, the composer and the page-side watcher.

[INPUT]
- tests.support.chrome_mcp_e2e (POS: Chrome page handles, the isolated runtime's UI and API urls)
- tests.support.chrome_skill_hooks_composer (POS: drive_chat_turn types and sends the request)
- tests.support.chrome_skill_hooks_live_e2e (POS: setup_skill_chat, SkillChat probe, DONE_TOKEN, audit_hooks)
- tests.support.hitl_live_e2e (POS: set_private_approval_timeout)

[OUTPUT]
- bash_request(): the user's request that makes the model call the bash tool once and then reply with the given answer, whether the command ran or was denied
- run_one_turn(): prepare the skill chat (and, when asked, the probe backend's approval timeout), send the request, hand the open page to a watcher
- SHORT_ANSWER: the answer asked for when the reply's content does not matter, only that it exists
- LONG_LIST_ANSWER: the answer asked for when the run must keep writing well past the few seconds a reload takes

[POS]
Shared by the approval-card Chrome E2E files (tests/e2e/test_approval_resume_reply_chrome_e2e.py, test_approval_timer_resume_chrome_e2e.py).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_api_url, get_e2e_ui_url
from tests.support.chrome_skill_hooks_composer import drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat, audit_hooks, setup_skill_chat
from tests.support.e2e_runtime_guard import E2EResourceLedger
from tests.support.hitl_live_e2e import set_private_approval_timeout

APPROVAL_PROBE_URL = "http://127.0.0.1:9/APPROVAL_RESUME_REPLY"
SHORT_ANSWER = f"reply with exactly: {DONE_TOKEN}"
# A long answer keeps the run working well past the few seconds a reload takes, whatever the model's speed.
_LONG_ANSWER_LINES = 600
LONG_LIST_ANSWER = (
    f"write the integers from 1 to {_LONG_ANSWER_LINES} as a bulleted list, one per bullet, "
    f"and after a blank line end with a last line of exactly: {DONE_TOKEN}"
)


def bash_request(answer: str) -> str:
    # One plain command keeps the turn at a single approval card.
    return (
        f"Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: "
        f"curl -sS {APPROVAL_PROBE_URL} . Run no other command. After it finishes, whatever its result, and even if it was "
        f"denied and never ran, {answer}"
    )


def run_one_turn(
    tmp_path: Path,
    e2e_resource_ledger: E2EResourceLedger,
    tag: str,
    request: str,
    watch: Callable[[ChromeMcpClient, McpPage, SkillChat, str], None],
    *,
    asks_approval: bool = True,
    approval_timeout_sec: int | None = None,
    approval_timeout_behavior: str = "deny",
    hooks_for: Callable[[Path], str] = audit_hooks,
) -> None:
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, tag, hooks_for, yolo=not asks_approval)
    if approval_timeout_sec is not None:
        # The probe's own backend only: the global setting the harness pins on the shared one keeps every other test's card waiting.
        set_private_approval_timeout(get_e2e_api_url(), approval_timeout_sec, approval_timeout_behavior)
    chat_url = f"{get_e2e_ui_url().rstrip('/')}{probe.ui_path}"
    drive_chat_turn(
        get_e2e_ui_url(),
        probe,
        request,
        invoke_skill=asks_approval,
        while_open=lambda client, page: watch(client, page, probe, chat_url),
    )
