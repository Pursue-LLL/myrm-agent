"""A destructive command waits for the user with the id of a workspace snapshot taken just before it.

Verifies, for the decision loop (a command the rules would let through, and one the rules ask about) and for the
YOLO branch:
1. The pending request carries the id of the snapshot of the working directory.
2. When no snapshot could be taken, the decision loop leaves the key out and the YOLO branch carries None.
"""

from __future__ import annotations

from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import ToolCall

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.audit import reset_audit_log
from myrm_agent_harness.agent.security.types import PermissionAction, PermissionRule, SecurityConfig

_SNAPSHOT = "myrm_agent_harness.toolkits.code_execution.security.workspace_snapshot.create_workspace_snapshot"

_ASKS = SecurityConfig(auto_mode_enabled=False)
_RULES_ALLOW = SecurityConfig(
    ruleset=(PermissionRule("code_interpreter", "*", PermissionAction.ALLOW),),
    auto_mode_enabled=False,
)
_YOLO = SecurityConfig(auto_mode_enabled=True, yolo_mode_enabled=True)


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_audit_log()
    approval_flow._allowlist = approval_flow.Allowlist()
    yield
    reset_audit_log()


async def _pending_context(config: SecurityConfig, session_key: str) -> dict[str, object]:
    call = ToolCall(
        type="tool_call",
        name="bash_code_execute_tool",
        args={"command": "rm -rf /tmp/destructive_gate_snapshot_dir"},
        id="tc_rm",
    )
    approved, denied, pending = await evaluate_tool_batch(
        [call],
        config,
        is_cron=False,
        workspace_root="/tmp",
        session_key=session_key,
        args_hashes={},
        is_interactive=True,
    )
    assert (len(approved), len(denied), len(pending)) == (0, 0, 1)
    return pending[0][4]


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [_ASKS, _RULES_ALLOW, _YOLO], ids=["rules-ask", "rules-allow", "yolo"])
async def test_pending_destructive_command_carries_the_snapshot_id(config: SecurityConfig) -> None:
    with patch(_SNAPSHOT, return_value=SimpleNamespace(snapshot_id="snap-1")) as create:
        context = await _pending_context(config, "snap-with-id")

    create.assert_called()
    assert context["snapshot_id"] == "snap-1"
    assert context["irreversible_destructive"] is True
    assert context["hide_allow_always"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("config", [_ASKS, _RULES_ALLOW], ids=["rules-ask", "rules-allow"])
async def test_decision_loop_leaves_the_snapshot_key_out_when_no_snapshot_was_taken(config: SecurityConfig) -> None:
    with patch(_SNAPSHOT, return_value=SimpleNamespace(snapshot_id=None)):
        context = await _pending_context(config, "snap-none")

    assert "snapshot_id" not in context
    assert context["irreversible_destructive"] is True


@pytest.mark.asyncio
async def test_yolo_branch_carries_none_when_no_snapshot_was_taken() -> None:
    with patch(_SNAPSHOT, return_value=SimpleNamespace(snapshot_id=None)):
        context = await _pending_context(_YOLO, "snap-yolo-none")

    assert context["snapshot_id"] is None
    assert context["irreversible_destructive"] is True
