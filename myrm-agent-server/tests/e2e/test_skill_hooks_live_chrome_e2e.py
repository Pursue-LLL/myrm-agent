"""Chrome LIVE E2E: command hooks of a user-installed skill govern a real WebUI chat turn.

Real business flow, no mocks and no API shortcut for the chat turn itself:

    local skill folder (SKILL.md with ``hooks:``) -> adopted into an agent
    -> user types ``/`` + the skill name in the composer, picks it from the slash palette (chip)
    -> user sends a message -> wire message ``[use <skill>] ...``
    -> live model calls the bash tool -> SessionStart / PreToolUse / PostToolUse / SessionEnd
       command hooks run on the host with the event payload delivered as ``$HOOK_PAYLOAD``.

What the hook side effects prove (they are written by the hooks, not by the model):
    - skill hooks are activated by an explicit ``[use skill]`` invocation (SessionStart payload),
    - the ``tools:`` filter reaches the real bash tool (PreToolUse/PostToolUse payload),
    - a third-party hook that the command gate refuses never runs (no marker),
    - a refused ``failure_mode: fail_closed`` PreToolUse hook blocks the tool call,
    - a tool call parked behind the approval card still runs the skill's hooks once the user approves
      (the resumed run re-activates them),
    - a message that carries an attachment (it reaches the agent as content blocks, not as plain text)
      invokes the skill and its hooks just the same,
    - a message too long for the model's context (the server spills it into a workspace file and leaves a
      reference behind) invokes the skill and its hooks just the same,
    - a follow-up message in the same chat that does not invoke the skill brings no hook back to life.

Formal run::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_skill_hooks_live_chrome_e2e.py::<test_name>
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.support.chrome_mcp_e2e import (
    ChromeMcpClient,
    McpPage,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
)
from tests.support.chrome_skill_hooks_composer import (
    TRANSCRIPT_CHIP_JS,
    TextAttachment,
    click_approve,
    describe_unanswered_resume,
    drive_chat_turn,
    wait_for_approval_card,
)
from tests.support.chrome_skill_hooks_live_e2e import (
    BASH_TOOL,
    BLOCKED_TOKEN,
    COMMAND_OUTPUT,
    DONE_TOKEN,
    audit_hooks,
    fail_closed_hooks,
    setup_skill_chat,
)
from tests.support.chrome_skill_hooks_observe import (
    assert_audit_turn_governed,
    assert_no_hook_raised,
    backend_log_offset,
    read_json,
    transcript_text,
    wait_assistant_reply_ending_with,
    wait_for_file,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger

# Port 9 (discard) refuses connections, so the command is harmless; curl to a URL is an UNKNOWN-risk shell command
# and therefore always parks behind the approval card.
_APPROVAL_PROBE_URL = "http://127.0.0.1:9/HOOKS_E2E_PROBE"

_FOLLOW_UP_OUTPUT = "FOLLOW-UP-OK"
_FOLLOW_UP_DONE_TOKEN = "HOOKS-E2E-FOLLOW-UP-DONE"

# The composer warns about a message longer than this and the Context Guard spills it into a workspace file.
_CONTEXT_GUARD_CAP_CHARS = 16_000
_BACKGROUND_NOTE_COUNT = 400


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_slash_invoked_skill_hooks_govern_a_live_turn(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "hookprobe", audit_hooks)

    drive_chat_turn(
        ui_url,
        probe,
        f"Run exactly this command with the bash tool: echo {COMMAND_OUTPUT} . "
        f"After it finishes, reply with exactly: {DONE_TOKEN}",
    )

    wait_assistant_reply_ending_with(probe.chat_id, api_url, DONE_TOKEN, timeout_sec=240.0)
    assert_audit_turn_governed(probe, api_url)

    # The user-facing transcript shows the skill as a chip, not the raw wire prefix.
    chat_url = f"{ui_url.rstrip('/')}{probe.ui_path}"
    with open_mcp_page(chat_url, timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=chat_url)
        state = wait_for_state(client, page, TRANSCRIPT_CHIP_JS, timeout_sec=90.0, page_url=chat_url)
        assert state.get("hasRawUsePrefix") is False, state


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_refused_fail_closed_hook_blocks_the_live_tool_call(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "guardprobe", fail_closed_hooks)
    out = probe.out

    drive_chat_turn(
        ui_url,
        probe,
        f"Run exactly this command with the bash tool: echo {COMMAND_OUTPUT} . "
        f"If the tool call is blocked or refused, reply with exactly: {BLOCKED_TOKEN} . "
        f"Otherwise reply with exactly: {DONE_TOKEN}",
    )

    reply = wait_assistant_reply_ending_with(probe.chat_id, api_url, BLOCKED_TOKEN, timeout_sec=240.0)

    # The benign hook registered before the guard ran, so the live bash call did reach PreToolUse.
    pre = read_json(out / "pre_tool_payload.json", api_url=api_url)
    assert pre.get("tool_name") == BASH_TOOL, pre

    # The refused fail_closed hook blocked the call: PostToolUse (only fired after a real run) never happened,
    # the refused command never executed, and the model was told the call was blocked by a hook.
    assert not (out / "post_tool_payload.json").exists()
    assert not (out / "escalated.marker").exists()
    assert DONE_TOKEN not in reply
    transcript = transcript_text(probe.chat_id, api_url)
    assert "Blocked by hook" in transcript, transcript[:2000]
    assert_no_hook_raised(probe, api_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_approved_tool_call_runs_the_skills_hooks_in_the_resumed_run(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "resumeprobe", audit_hooks, yolo=False)
    out = probe.out
    parked: dict[str, object] = {}

    def approve_then_wait_for_reply(client: ChromeMcpClient, page: McpPage) -> None:
        wait_for_approval_card(client, page)
        # The run is parked at its HITL interrupt: SessionStart already ran, the tool call has not.
        parked["session"] = read_json(out / "session_payload.json", api_url=api_url)
        parked["pre_tool_payload_exists"] = (out / "pre_tool_payload.json").exists()
        log_offset = backend_log_offset(api_url)
        click_approve(client, page)
        # Keep the page open until the resumed run has streamed its answer.
        try:
            parked["reply"] = wait_assistant_reply_ending_with(probe.chat_id, api_url, DONE_TOKEN, timeout_sec=240.0)
        except pytest.fail.Exception as failure:
            pytest.fail(describe_unanswered_resume(failure, client, page, probe, log_offset=log_offset))

    drive_chat_turn(
        ui_url,
        probe,
        f"Run exactly this command with the bash tool: curl -sS {_APPROVAL_PROBE_URL} . "
        f"After it finishes, whatever its result, reply with exactly: {DONE_TOKEN}",
        while_open=approve_then_wait_for_reply,
    )
    wait_for_file(out / "post_tool_payload.json", api_url=api_url)

    # Before the click: first run only (is_resume False), tool hook not yet run.
    parked_session = parked["session"]
    assert isinstance(parked_session, dict) and parked_session.get("is_resume") is False, parked
    assert parked["pre_tool_payload_exists"] is False, parked

    # After the click the resumed run re-activated the skill's hooks: SessionStart saw the resume,
    # and the approved bash call went through PreToolUse and PostToolUse.
    session_payload = read_json(out / "session_payload.json", api_url=api_url)
    assert session_payload.get("is_resume") is True, session_payload
    pre = read_json(out / "pre_tool_payload.json", api_url=api_url)
    assert pre.get("tool_name") == BASH_TOOL, pre
    assert _APPROVAL_PROBE_URL in json.dumps(pre.get("tool_input")), pre
    post = read_json(out / "post_tool_payload.json", api_url=api_url)
    assert post.get("tool_name") == BASH_TOOL, post
    assert not (out / "escalated.marker").exists()
    assert_no_hook_raised(probe, api_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_slash_invoked_skill_governs_a_turn_that_carries_an_attachment(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "attachprobe", audit_hooks)
    notes = TextAttachment(name="field-notes.txt", text="Context for the request: nothing here needs any action.")

    drive_chat_turn(
        ui_url,
        probe,
        f"Run exactly this command with the bash tool: echo {COMMAND_OUTPUT} . "
        f"After it finishes, reply with exactly: {DONE_TOKEN}",
        attachment=notes,
    )

    wait_assistant_reply_ending_with(probe.chat_id, api_url, DONE_TOKEN, timeout_sec=240.0)
    assert_audit_turn_governed(probe, api_url)
    assert notes.name in transcript_text(probe.chat_id, api_url), "the attachment travelled with the invoking turn"


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_slash_invoked_skill_governs_a_turn_whose_message_is_spilled_to_a_file(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "spillprobe", audit_hooks)
    background = "\n".join(
        f"Background note {index}: nothing in this line needs any action." for index in range(_BACKGROUND_NOTE_COUNT)
    )
    request = (
        f"Run exactly this command with the bash tool: echo {COMMAND_OUTPUT} . "
        f"After it finishes, reply with exactly: {DONE_TOKEN}\n\n{background}"
    )
    assert len(request) > _CONTEXT_GUARD_CAP_CHARS

    # The server keeps the invocation tag in front of the file reference it stores for the oversized message.
    drive_chat_turn(ui_url, probe, request, spilled=True)

    wait_assistant_reply_ending_with(probe.chat_id, api_url, DONE_TOKEN, timeout_sec=240.0)
    assert_audit_turn_governed(probe, api_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_follow_up_turn_without_the_skill_runs_no_hooks(tmp_path: Path, e2e_resource_ledger: E2EResourceLedger) -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    probe = setup_skill_chat(tmp_path, e2e_resource_ledger, "followprobe", audit_hooks)
    out = probe.out

    drive_chat_turn(
        ui_url,
        probe,
        f"Run exactly this command with the bash tool: echo {COMMAND_OUTPUT} . "
        f"After it finishes, reply with exactly: {DONE_TOKEN}",
    )
    wait_assistant_reply_ending_with(probe.chat_id, api_url, DONE_TOKEN, timeout_sec=240.0)
    assert_audit_turn_governed(probe, api_url)
    governed = {path.name: path.read_text(encoding="utf-8") for path in out.iterdir()}

    # The user keeps chatting in the same chat without invoking the skill; the model runs another bash call.
    wire = drive_chat_turn(
        ui_url,
        probe,
        f"Now run exactly this command with the bash tool: echo {_FOLLOW_UP_OUTPUT} . "
        f"After it finishes, reply with exactly: {_FOLLOW_UP_DONE_TOKEN}",
        invoke_skill=False,
    )
    assert not wire.startswith("[use "), wire
    wait_assistant_reply_ending_with(probe.chat_id, api_url, _FOLLOW_UP_DONE_TOKEN, timeout_sec=240.0)

    # The follow-up really ran its bash call, but the skill was invoked for the first turn only: its hooks
    # saw nothing of the second one (a leaked PreToolUse/PostToolUse/SessionEnd hook would have rewritten
    # a payload or added an audit line).
    assert _FOLLOW_UP_OUTPUT in transcript_text(probe.chat_id, api_url)
    assert {path.name: path.read_text(encoding="utf-8") for path in out.iterdir()} == governed
    assert_no_hook_raised(probe, api_url)
