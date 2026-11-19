"""The pauses a kanban run's stream can end on, built the way a paused agent run emits them.

[INPUT]
- myrm_agent_harness interrupt_events + build_interrupt_payload + ToolStuckException + CodedReason (POS: the events and
  payloads the real harness produces for a pause, so no test types an approval payload by hand)

[OUTPUT]
- TASK_ID: the task every pause is addressed to
- paused_on: the stream event the harness emits when the graph pauses on an interrupt value
- approval_pause: the stream event of a run paused on a tool approval card that holds the given calls
- TOOL_APPROVAL / HELD_APPROVAL / MIXED_APPROVAL / OTHER_APPROVAL / BROWSER_TAKEOVER / LOOP_GUARD_PAUSE: the pauses
  a kanban run meets (an ordinary approval; one a person alone may answer; a card holding both; a semantic browser
  approval; a login or captcha step; the loop guard's pause, which asks nothing)

[POS]
Shared by the kanban run tests that pin what each pause means for a task and for the reason the task is blocked with.
"""

from __future__ import annotations

from collections.abc import Mapping

from langchain_core.messages import ToolCall
from langgraph.types import Interrupt
from myrm_agent_harness.agent.errors import ToolStuckException
from myrm_agent_harness.agent.middlewares.approval.batch_processor import build_interrupt_payload
from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode, CodedReason
from myrm_agent_harness.agent.streaming.interrupt_events import interrupt_events

TASK_ID = "task0001"

# One pending call of a card: the call, its permission type, the reason it waits under, and its approval context.
PendingCall = tuple[ToolCall, str, str, dict[str, object] | None]


def paused_on(interrupt_value: Mapping[str, object]) -> dict[str, object]:
    """The stream event the harness emits when the graph pauses on this interrupt value."""
    return interrupt_events([Interrupt(value=interrupt_value, id="interrupt-1")], "message-1")[0]


def approval_pause(*calls: PendingCall) -> dict[str, object]:
    """The stream event of a run paused on one tool approval card that holds ``calls``."""
    pending = [(idx, call, permission, reason, context) for idx, (call, permission, reason, context) in enumerate(calls)]
    return paused_on(build_interrupt_payload(pending, f"kanban:{TASK_ID}")[0])


SHELL_CALL: ToolCall = {"name": "shell_exec", "args": {"command": "rm -rf build"}, "id": "call-1", "type": "tool_call"}
HOOK_CALL: ToolCall = {
    "name": "file_write_tool",
    "args": {"path": ".git/hooks/pre-commit", "content": "#!/bin/sh\n"},
    "id": "call-2",
    "type": "tool_call",
}
_HOOK_REASON = CodedReason(
    "Git hook or config write requires human approval: .git/hooks/pre-commit",
    ApprovalReasonCode.GIT_METADATA_WRITE,
    ".git/hooks/pre-commit",
)

ORDINARY_CALL: PendingCall = (SHELL_CALL, "shell_exec", "requires approval", None)
HELD_CALL: PendingCall = (HOOK_CALL, "file_write", _HOOK_REASON, None)

TOOL_APPROVAL = approval_pause(ORDINARY_CALL)
HELD_APPROVAL = approval_pause(HELD_CALL)
MIXED_APPROVAL = approval_pause(ORDINARY_CALL, HELD_CALL)
OTHER_APPROVAL = paused_on(
    {"action_type": "high_risk_dom_action", "tool_name": "browser_click", "reason": "Submits a payment form"}
)
# What `browser_ask_human` raises when the agent meets a login or a captcha.
BROWSER_TAKEOVER = paused_on(
    {"action_type": "browser_takeover", "tool_name": "browser_ask_human_tool", "reason": "Log in to continue"}
)
LOOP_GUARD_PAUSE = paused_on(ToolStuckException("The same call failed 5 times").interrupt_payload("shell_exec", "call-1"))
