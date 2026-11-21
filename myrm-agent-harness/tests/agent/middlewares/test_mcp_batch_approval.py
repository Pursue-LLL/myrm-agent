"""Tests for MCP approval in batch_processor (non-PTC path).

A direct MCP tool call (not via bash_code_execute_tool/PTC) always asks: what a server declares about a tool never
skips the approval prompt, whatever record the registry holds for it.
"""

import pytest
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.security.tool_registry import SafetyMetadata
from myrm_agent_harness.agent.security.types import (
    PathPolicy,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)
from myrm_agent_harness.core.security.tool_registry import register_ptc_safety_metadata

_LOOKS_READ_ONLY = SafetyMetadata(is_read_only=True, is_concurrent_safe=True, is_idempotent=True)
"""The loosest record: no server claim can produce it, and no gate may read it as permission."""


def _hold(tool_name: str, record: SafetyMetadata) -> None:
    """Put ``record`` in the registry where a direct call to ``tool_name`` resolves it."""
    register_ptc_safety_metadata("mcp_server_skill", tool_name, record, {})


async def _decide(*tool_calls: ToolCall, config: SecurityConfig | None = None) -> tuple[list, list, list]:
    return await evaluate_tool_batch(
        tool_calls=list(tool_calls),
        config=config or SecurityConfig(auto_mode_enabled=False, path_policy=PathPolicy()),
        is_cron=False,
        workspace_root="/workspace",
        session_key="test_sess",
        args_hashes={},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "record",
    [
        _LOOKS_READ_ONLY,
        SafetyMetadata(is_read_only=True, is_destructive=True, is_concurrent_safe=True),
        SafetyMetadata(is_destructive=True),
    ],
    ids=["looks-read-only", "read-only-and-destructive", "destructive"],
)
async def test_mcp_tool_stays_pending_whatever_the_registry_holds(record: SafetyMetadata) -> None:
    _hold("mcp__gmail__search_inbox", record)

    auto_approved, auto_denied, pending = await _decide(
        ToolCall(name="mcp__gmail__search_inbox", args={"query": "from:zhang@example.com"}, id="call_1")
    )

    assert (len(auto_approved), len(auto_denied), len(pending)) == (0, 0, 1)


@pytest.mark.asyncio
async def test_mcp_unknown_tool_stays_pending():
    """An MCP tool with no registered record stays in pending (fail-closed)."""
    auto_approved, auto_denied, pending = await _decide(
        ToolCall(name="mcp__unknown_server__mystery_tool", args={}, id="call_unknown")
    )

    assert (len(auto_approved), len(auto_denied), len(pending)) == (0, 0, 1)


@pytest.mark.asyncio
async def test_mcp_batch_stays_pending_call_by_call():
    """A record that looks read-only on one call of a batch does not carry over to the others."""
    _hold("mcp__gmail__search_inbox", _LOOKS_READ_ONLY)

    auto_approved, auto_denied, pending = await _decide(
        ToolCall(name="mcp__gmail__search_inbox", args={"query": "test"}, id="call_read"),
        ToolCall(name="mcp__gmail__send_email", args={"to": "a@b.com"}, id="call_write"),
    )

    assert (len(auto_approved), len(auto_denied)) == (0, 0)
    assert [call[1].get("id") for call in pending] == ["call_read", "call_write"]


@pytest.mark.asyncio
async def test_mcp_denied_by_rule_not_overridden():
    """A per-tool DENY rule is respected, with or without a record that looks read-only."""
    _hold("mcp__gmail__search_inbox", _LOOKS_READ_ONLY)
    ruleset = (PermissionRule("mcp_invoke", "mcp__gmail__*", PermissionAction.DENY),)

    auto_approved, auto_denied, pending = await _decide(
        ToolCall(name="mcp__gmail__search_inbox", args={"query": "test"}, id="call_denied"),
        config=SecurityConfig(auto_mode_enabled=False, path_policy=PathPolicy(), ruleset=ruleset),
    )

    assert (len(auto_approved), len(auto_denied), len(pending)) == (0, 1, 0)


@pytest.mark.asyncio
async def test_desktop_vision_operator_key_auto_denied_before_hitl():
    """Lone operator as vision key is auto-denied (no approval card)."""
    config = SecurityConfig(auto_mode_enabled=False, path_policy=PathPolicy())
    tool_call = ToolCall(
        name="desktop_vision_tool",
        args={"action": "key", "text": "*"},
        id="call_op_key",
    )
    auto_approved, auto_denied, pending = await evaluate_tool_batch(
        tool_calls=[tool_call],
        config=config,
        is_cron=False,
        workspace_root="/workspace",
        session_key="test_op_key",
        args_hashes={},
    )
    assert len(auto_approved) == 0
    assert len(pending) == 0
    assert len(auto_denied) == 1
    _idx, _tc, msg = auto_denied[0]
    assert "Rejected printable operator" in msg
    assert "REMEDY_HINT" in msg


def test_operator_as_key_deny_message_allows_modifier_combo():
    from myrm_agent_harness.agent.middlewares.approval.batch_processor import (
        operator_as_key_deny_message,
    )

    assert operator_as_key_deny_message("desktop_vision_tool", {"action": "key", "text": "ctrl+/"}) is None
    assert operator_as_key_deny_message("desktop_vision_tool", {"action": "type", "text": "*"}) is None
