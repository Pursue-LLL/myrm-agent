"""Tests approval payload extraction for flat LangGraph interrupt payloads."""

from __future__ import annotations


def _extract_approval_payload(approval_data: dict[str, object]) -> dict[str, object]:
    """Mirror streaming.py flat-interrupt payload extraction."""
    nested_payload = approval_data.get("payload")
    if isinstance(nested_payload, dict) and nested_payload:
        return dict(nested_payload)
    _meta_keys = frozenset(
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
    return {k: v for k, v in approval_data.items() if k not in _meta_keys and v is not None}


class TestExtractApprovalPayload:
    def test_nested_payload_passthrough(self) -> None:
        data = {
            "action_type": "skill_draft",
            "payload": {"content": "patch", "artifact_id": "a1"},
            "reason": "review",
        }
        result = _extract_approval_payload(data)
        assert result == {"content": "patch", "artifact_id": "a1"}

    def test_flat_semantic_dom_interrupt(self) -> None:
        expr = "document.querySelector('.pay').click()"
        data: dict[str, object] = {
            "action_type": "high_risk_dom_action",
            "tool_name": "browser_manage_tool",
            "tool_input": {"action": "evaluate", "expression": expr},
            "page_url": "https://shop.example.com",
            "reason": "Mutating JS evaluate",
        }
        result = _extract_approval_payload(data)
        assert result["tool_input"] == {"action": "evaluate", "expression": expr}
        assert result["page_url"] == "https://shop.example.com"
        assert result["tool_name"] == "browser_manage_tool"
        assert "action_type" not in result
