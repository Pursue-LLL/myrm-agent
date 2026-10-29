"""Helpers for persisting LangGraph interrupt payloads as approval records.

[INPUT]
- LangGraph interrupt dict from streaming bridge (flat or nested ``payload``)
- myrm_agent_harness.agent.errors::TOOL_STUCK_ACTION_TYPE (POS: action_type of the interrupt a loop guard pause raises)

[OUTPUT]
- extract_approval_registry_payload: ApprovalRegistry payload SSOT for SSE interrupts
- is_tool_stuck_pause: whether an interrupt is a loop guard pause, which is no approval

[POS]
Shared approval payload normalization for streaming.py, the stream collector, the voice bridge, the channel stream
mapper, the phase stepper and approval persistence tests. The web app and the browser extension side panel tell a loop
guard pause apart on the client by the same ``action_type``.
"""

from __future__ import annotations

from myrm_agent_harness.agent.errors import TOOL_STUCK_ACTION_TYPE

_APPROVAL_META_KEYS = frozenset(
    {
        "approval_id",
        "severity",
        "reason",
        "action_type",
        "type",
        "messageId",
        "chat_id",
        "user_id",
        "status",
        "expires_at",
        "thread_id",
        "payload",
    }
)


def is_tool_stuck_pause(interrupt_data: object) -> bool:
    """True for the loop guard's pause: the run stopped on repeated tool failures.

    It reaches the stream as an ``approval_required`` event, but nothing waits on an answer: a new message from the
    user continues the chat. So it is no approval record and no turn left open.
    """
    return isinstance(interrupt_data, dict) and interrupt_data.get("action_type") == TOOL_STUCK_ACTION_TYPE


def extract_approval_registry_payload(approval_data: dict[str, object]) -> dict[str, object]:
    """Return payload dict for ApprovalRegistry from SSE interrupt data.

    Nested ``payload`` wins when present. Flat semantic DOM HITL interrupts
    (``tool_input``, ``element``, ``page_url`` at top level) are folded in.
    """
    nested_payload = approval_data.get("payload")
    if isinstance(nested_payload, dict) and nested_payload:
        return dict(nested_payload)
    return {k: v for k, v in approval_data.items() if k not in _APPROVAL_META_KEYS and v is not None}
