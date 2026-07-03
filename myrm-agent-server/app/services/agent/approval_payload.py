"""Helpers for persisting LangGraph interrupt payloads as approval records.

[INPUT]
- LangGraph interrupt dict from streaming bridge (flat or nested ``payload``)

[OUTPUT]
- extract_approval_registry_payload: ApprovalRegistry payload SSOT for SSE interrupts

[POS]
Shared approval payload normalization for streaming.py and approval persistence tests.
"""

from __future__ import annotations

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


def extract_approval_registry_payload(approval_data: dict[str, object]) -> dict[str, object]:
    """Return payload dict for ApprovalRegistry from SSE interrupt data.

    Nested ``payload`` wins when present. Flat semantic DOM HITL interrupts
    (``tool_input``, ``element``, ``page_url`` at top level) are folded in.
    """
    nested_payload = approval_data.get("payload")
    if isinstance(nested_payload, dict) and nested_payload:
        return dict(nested_payload)
    return {
        k: v for k, v in approval_data.items() if k not in _APPROVAL_META_KEYS and v is not None
    }
