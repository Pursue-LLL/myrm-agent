"""Chrome LIVE E2E: the reply of an approved run appears on the page the user is watching, and is still there after a reload.

Real business flow, no mocks and no API shortcut for the chat turn itself:

    user sends a message -> live model calls the bash tool -> the run parks behind the approval card
    -> user presses Approve -> the page sends the resume under the id of the turn that asked
    -> the response to that request is the rest of the turn: the tool runs and the model answers
    -> the user reloads the chat and the stored reply is there.

A server that answers the resume with the buffered events of the stopped turn leaves the page with a finished-looking turn and no
answer: the run does finish (its reply is stored), and the user sees it only after reloading the chat.

The second test presses Approve and reloads the page 1.5 s later, while the resumed run is still working: the run must go on without the
page that sent the resume, and the reloaded chat ends with its reply.

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
    get_e2e_ui_url,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
)
from tests.support.chrome_skill_hooks_approval import approve_cards_until_reply, click_approve, wait_for_approval_card
from tests.support.chrome_skill_hooks_composer import describe_page, drive_chat_turn
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat, audit_hooks, setup_skill_chat
from tests.support.e2e_runtime_guard import E2EResourceLedger

_APPROVAL_PROBE_URL = "http://127.0.0.1:9/APPROVAL_RESUME_REPLY"
# The stored reply is there seconds after the click; the page gets the same time to show it, live and after a reload.
_REPLY_ON_PAGE_TIMEOUT_SEC = 60.0
_RELOAD_TIMEOUT_MS = 90_000
_RELOAD_AFTER_APPROVE_SEC = 1.5

# A flag on the window lives exactly as long as the document: it proves the reload replaced the page the reply was streamed to.
_MARK_DOCUMENT_JS = "(() => { window.__MYRM_E2E_BEFORE_RELOAD__ = true; return true; })()"
_DOCUMENT_IS_MARKED_JS = "window.__MYRM_E2E_BEFORE_RELOAD__ === true"

# The answer is a line of its own; the user's message that asks for it is a longer line.
_REPLY_ON_PAGE_JS = (
    f"""(() => (document.body?.innerText ?? '').split('\\n').some((line) => line.trim() === {json.dumps(DONE_TOKEN)}))()"""
)


def _reply_on_page(client: ChromeMcpClient, page: McpPage) -> bool:
    return client.evaluate(page, _REPLY_ON_PAGE_JS, timeout_sec=15.0) is True


def _wait_for_reply_on_page(client: ChromeMcpClient, page: McpPage, failure: str) -> None:
    deadline = time.monotonic() + _REPLY_ON_PAGE_TIMEOUT_SEC
    while time.monotonic() < deadline:
        if _reply_on_page(client, page):
            return
        time.sleep(1.0)
    pytest.fail(f"{failure} within {_REPLY_ON_PAGE_TIMEOUT_SEC:.0f}s\n{describe_page(client, page)}")


def _reload_the_chat(client: ChromeMcpClient, page: McpPage, chat_url: str) -> None:
    assert client.evaluate(page, _MARK_DOCUMENT_JS, timeout_sec=15.0) is True
    reload_mcp_page(client, page, target_url=chat_url, timeout_ms=_RELOAD_TIMEOUT_MS)
    wait_for_react_e2e_bridge(client, page, timeout_sec=90.0, page_url=chat_url)
    assert client.evaluate(page, _DOCUMENT_IS_MARKED_JS, timeout_sec=15.0) is False, "the page was not reloaded"


def _run_one_approval_turn(
    tmp_path: Path,
    e2e_resource_ledger: E2EResourceLedger,
    tag: str,
    watch: Callable[[ChromeMcpClient, McpPage, SkillChat, str], None],
) -> None:
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, tag, audit_hooks, yolo=False)
    chat_url = f"{get_e2e_ui_url().rstrip('/')}{probe.ui_path}"

    # One plain command keeps the turn at a single approval card.
    drive_chat_turn(
        get_e2e_ui_url(),
        probe,
        f"Run exactly this one plain command with the bash tool, with no ';', '&&', pipe or redirect: "
        f"curl -sS {_APPROVAL_PROBE_URL} . Run no other command. "
        f"After it finishes, whatever its result, reply with exactly: {DONE_TOKEN}",
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
        _wait_for_reply_on_page(client, page, "the reply of the approved run is stored but the page did not show it")
        _reload_the_chat(client, page, chat_url)
        _wait_for_reply_on_page(client, page, "after a reload the chat did not show the stored reply of the approved run")

    _run_one_approval_turn(tmp_path, e2e_resource_ledger, "resumereply", approve_then_watch_the_page)


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
        # The tool and the model's answer take seconds, so the run is still working when the page goes away.
        time.sleep(_RELOAD_AFTER_APPROVE_SEC)
        assert not _reply_on_page(client, page), "the run had already answered; the reload would not interrupt anything"
        _reload_the_chat(client, page, chat_url)
        # A click that never reached the server leaves the card on the reloaded page; the user approves it again.
        approve_cards_until_reply(client, page, probe, DONE_TOKEN, timeout_sec=240.0, tolerate_closing_note=True)
        _wait_for_reply_on_page(client, page, "after reloading mid-run the chat did not show the reply of the approved run")

    _run_one_approval_turn(tmp_path, e2e_resource_ledger, "reloadmid", approve_then_reload_mid_run)
