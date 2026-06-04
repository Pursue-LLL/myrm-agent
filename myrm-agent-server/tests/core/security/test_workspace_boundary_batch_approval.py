"""Deterministic workspace boundary approval tests (no LLM)."""

from __future__ import annotations

import pytest
from langchain_core.messages import ToolCall
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig


@pytest.mark.asyncio
async def test_out_of_bounds_file_write_goes_to_pending_approval() -> None:
    """Path outside workspace must surface as batch pending approval, not auto-execute."""
    config = SecurityConfig(
        yolo_mode_enabled=False,
        auto_mode_enabled=False,
    )
    workspace_root = "/tmp/myrm_agent_workspace_only"
    tool_calls = [
        ToolCall(
            type="tool_call",
            name="file_write_tool",
            args={"path": "/var/myrm_oob_integration_test.txt", "content": "hello"},
            id="call_oob_1",
        )
    ]

    approved, denied, pending = await evaluate_tool_batch(
        tool_calls,
        config,
        is_cron=False,
        workspace_root=workspace_root,
        session_key="integration-test",
        args_hashes={},
    )

    assert not approved
    assert not denied
    assert len(pending) == 1
    _idx, _call, _permission, reason, _extra = pending[0]
    assert "Path outside allowed zones" in reason


@pytest.mark.asyncio
async def test_in_workspace_file_write_is_auto_allowed() -> None:
    """Writes inside workspace root should not require HITL when ruleset allows."""
    config = SecurityConfig(
        yolo_mode_enabled=False,
        auto_mode_enabled=False,
    )
    workspace_root = "/tmp/myrm_agent_workspace_only"
    tool_calls = [
        ToolCall(
            type="tool_call",
            name="file_write_tool",
            args={"path": "notes/hello.txt", "content": "hello"},
            id="call_in_1",
        )
    ]

    approved, denied, pending = await evaluate_tool_batch(
        tool_calls,
        config,
        is_cron=False,
        workspace_root=workspace_root,
        session_key="integration-test-in",
        args_hashes={},
    )

    assert len(approved) == 1
    assert not denied
    assert not pending
