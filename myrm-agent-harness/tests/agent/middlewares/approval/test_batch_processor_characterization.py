"""Characterization tests for the batch approval decision table.

Each test pins the observable classification (approved / denied / pending) for one
decision branch. They exist to keep the behaviour stable while the 1000-line
``evaluate_tool_batch`` function is split into smaller units.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.middlewares.approval import (
    set_approval_session,
    set_approval_user_id,
    set_security_config,
    set_workspace_root,
)
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.types import (
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)


@pytest.fixture(autouse=True)
def _clean_state():
    reset_denial_counter()
    reset_taint_tracker()
    yield
    reset_denial_counter()
    reset_taint_tracker()


def _ask_config(*, yolo: bool = False) -> SecurityConfig:
    return SecurityConfig(
        ruleset=(PermissionRule("*", "*", PermissionAction.ASK),),
        yolo_mode_enabled=yolo,
    )


def _install_session(config: SecurityConfig) -> None:
    set_security_config(config)
    set_workspace_root("/tmp")
    set_approval_session("characterization-session")
    set_approval_user_id("user1")


@pytest.mark.asyncio
async def test_yolo_denies_lone_operator_key_before_hitl() -> None:
    """YOLO must not auto-approve a printable operator used as a key name."""
    config = _ask_config(yolo=True)
    _install_session(config)
    calls = [{"name": "desktop_vision_tool", "args": {"action": "key", "text": "+"}, "id": "c1"}]

    with patch(
        "myrm_agent_harness.agent.security.managed_policy_gates.yolo_allowed_for_model",
        return_value=True,
    ):
        approved, denied, pending = await evaluate_tool_batch(calls, config, False, "/tmp", "s", {})

    assert approved == []
    assert pending == []
    assert len(denied) == 1
    assert "Printable operators are not keyboard key names" in denied[0][2]


@pytest.mark.asyncio
async def test_interactive_ask_yields_pending_not_approved() -> None:
    """A plain ASK rule without YOLO stays pending for the user."""
    config = _ask_config()
    _install_session(config)
    calls = [{"name": "file_read_tool", "args": {"path": "/tmp/x"}, "id": "c1"}]

    approved, denied, pending = await evaluate_tool_batch(calls, config, False, "/tmp", "s", {})

    assert approved == []
    assert denied == []
    assert len(pending) == 1
    idx, call, permission_type, reason, _context = pending[0]
    assert idx == 0 and call is calls[0]
    assert permission_type
    assert reason == ""


@pytest.mark.asyncio
async def test_repo_declared_prefix_auto_approves_trusted_shell() -> None:
    """A TRUSTED repo prefix turns an ASK shell command into an approval."""
    config = _ask_config()
    _install_session(config)
    calls = [{"name": "bash_code_execute_tool", "args": {"command": "pytest -q"}, "id": "c1"}]

    with (
        patch(
            "myrm_agent_harness.agent.security.command_allowlist_pattern.extract_shell_command",
            return_value="pytest -q",
        ),
        patch(
            "myrm_agent_harness.agent.security.workspace_trust.context.get_workspace_trust_level",
            return_value=3,
        ),
        patch(
            "myrm_agent_harness.agent.security.workspace_trust.context.get_repo_command_prefixes",
            return_value=("pytest",),
        ),
        patch(
            "myrm_agent_harness.agent.security.workspace_trust.gate.matches_repo_command_prefix",
            return_value=True,
        ),
    ):
        approved, denied, pending = await evaluate_tool_batch(calls, config, False, "/tmp", "s", {})

    assert len(approved) == 1
    assert denied == []
    assert pending == []
