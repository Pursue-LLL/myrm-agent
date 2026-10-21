"""Tests extract_approval_registry_payload for flat LangGraph interrupt payloads."""

from __future__ import annotations

from app.services.agent.approval_payload import extract_approval_registry_payload


class TestExtractApprovalRegistryPayload:
    def test_nested_payload_passthrough(self) -> None:
        data = {
            "action_type": "skill_draft",
            "payload": {"content": "patch", "artifact_id": "a1"},
            "reason": "review",
        }
        result = extract_approval_registry_payload(data)
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
        result = extract_approval_registry_payload(data)
        assert result["tool_input"] == {"action": "evaluate", "expression": expr}
        assert result["page_url"] == "https://shop.example.com"
        assert result["tool_name"] == "browser_manage_tool"
        assert "action_type" not in result

    def test_empty_nested_payload_falls_back_to_flat(self) -> None:
        data: dict[str, object] = {
            "action_type": "high_risk_dom_action",
            "payload": {},
            "tool_input": {"action": "click", "ref": "e1"},
        }
        result = extract_approval_registry_payload(data)
        assert result["tool_input"] == {"action": "click", "ref": "e1"}

    def test_flat_click_interrupt_includes_element(self) -> None:
        data: dict[str, object] = {
            "action_type": "high_risk_dom_action",
            "tool_name": "browser_interact_tool",
            "tool_input": {"action": "click", "ref": "e5", "text": ""},
            "element": {"role": "button", "name": "Delete Repository", "ref": "e5"},
            "page_url": "https://github.com/settings",
            "reason": "High-risk click",
        }
        result = extract_approval_registry_payload(data)
        assert result["element"] == data["element"]
        assert result["page_url"] == "https://github.com/settings"

    def test_flat_payload_drops_none_meta_values(self) -> None:
        data: dict[str, object] = {
            "action_type": "high_risk_dom_action",
            "tool_input": {"action": "evaluate", "expression": "document.title"},
            "page_url": None,
            "reason": "read-only skipped",
        }
        result = extract_approval_registry_payload(data)
        assert "page_url" not in result
        assert result["tool_input"] == {"action": "evaluate", "expression": "document.title"}
