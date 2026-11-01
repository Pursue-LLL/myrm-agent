"""Tests for MCP proxy required-argument validation."""

from __future__ import annotations

from myrm_agent_harness.agent.skills.mcp.proxy_service import (
    _missing_required_params_error,
)


class TestMissingRequiredParamsError:
    def test_missing_required_describes_the_call_with_a_pasteable_signature(self) -> None:
        schema_entry = {
            "description": "Create issue",
            "inputSchema": {
                "type": "object",
                "properties": {"title": {"type": "string"}, "body": {"type": "string"}},
                "required": ["title"],
            },
        }
        message = _missing_required_params_error("create_issue", {}, schema_entry)
        assert message is not None
        assert "Missing required argument(s): title" in message
        assert "The tool was NOT invoked" in message
        assert "create_issue(*, title:string, body?:string)" in message

    def test_message_speaks_ptc_not_function_calling(self) -> None:
        schema_entry = {"inputSchema": {"type": "object", "properties": {"q": {"type": "string"}}, "required": ["q"]}}
        message = _missing_required_params_error("search", {}, schema_entry)
        assert message is not None
        assert "tool_call" not in message
        assert "'arguments'" not in message

    def test_all_required_present_returns_none(self) -> None:
        schema_entry = {
            "inputSchema": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        }
        assert _missing_required_params_error("create_issue", {"title": "bug"}, schema_entry) is None

    def test_no_required_field_returns_none(self) -> None:
        schema_entry = {"inputSchema": {"type": "object", "properties": {}}}
        assert _missing_required_params_error("ping", {}, schema_entry) is None
