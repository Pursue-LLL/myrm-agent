"""Integration: external_cli entitlement via agent-stream tools_snapshot."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection


def _tools_snapshot_event(events: list[dict[str, object]]) -> dict[str, object] | None:
    snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
    return snapshot if isinstance(snapshot, dict) else None


def _tool_names_from_snapshot(events: list[dict[str, object]]) -> set[str]:
    tools_snapshot = _tools_snapshot_event(events)
    if tools_snapshot is None:
        return set()
    snapshot_rows = tools_snapshot.get("data")
    if not isinstance(snapshot_rows, list):
        return set()
    return {str(row.get("name")) for row in snapshot_rows if isinstance(row, dict) and row.get("name")}


def _enabled_builtin_from_snapshot(events: list[dict[str, object]]) -> list[str] | None:
    tools_snapshot = _tools_snapshot_event(events)
    if tools_snapshot is None:
        return None
    snapshot_data = tools_snapshot.get("data")
    if not isinstance(snapshot_data, dict):
        return None
    enabled = snapshot_data.get("enabled_builtin_tools")
    return list(enabled) if isinstance(enabled, list) else None


def _external_cli_payload(chat_id: str, *, include_external_cli: bool) -> dict[str, object]:
    enabled = ["web_search", "memory"]
    if include_external_cli:
        enabled.append("external_cli")
    return {
        "query": "Reply with the word OK only.",
        "message_id": f"test-ext-cli-{chat_id}",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": enabled,
            "skill_ids": [],
        },
        "timezone": "UTC",
    }


@pytest.mark.e2e
def test_agent_stream_external_cli_off_excludes_delegate_tool(
    client: TestClient,
) -> None:
    """Writer-style profile without external_cli must not mount invoke_acp_agent_tool Turn1."""
    chat_id = f"test_ext_cli_off_{uuid.uuid4().hex[:8]}"
    events = _collect_agent_stream(client, _external_cli_payload(chat_id, include_external_cli=False))
    check_e2e_errors(events)

    tool_names = _tool_names_from_snapshot(events)
    if tool_names:
        assert "invoke_acp_agent_tool" not in tool_names


@pytest.mark.e2e
@patch(
    "app.ai_agents.general_agent.external_agents._resolve_external_agent_cfgs",
    new=AsyncMock(return_value=[{"name": "echo-cli", "type": "cli", "command": "echo", "args": []}]),
)
def test_agent_stream_external_cli_on_mounts_delegate_when_backends_exist(
    client: TestClient,
) -> None:
    """external_cli ON + resolvable CLI backends must expose invoke_acp_agent_tool Turn1."""
    chat_id = f"test_ext_cli_on_{uuid.uuid4().hex[:8]}"
    events = _collect_agent_stream(client, _external_cli_payload(chat_id, include_external_cli=True))
    check_e2e_errors(events)

    tool_names = _tool_names_from_snapshot(events)
    if tool_names:
        assert "invoke_acp_agent_tool" in tool_names


@pytest.mark.e2e
def test_explore_security_preset_denies_invoke_external_in_merged_config() -> None:
    """Lane-C regression: explore preset must deny invoke_external_agent (readonly-class bug)."""
    from app.services.agent.params.converter import _apply_session_preset

    base: dict[str, object] = {
        "permissions": {
            "spawn_subagent": "allow",
            "invoke_external_agent": "allow",
        }
    }
    merged = _apply_session_preset(base, "explore")
    assert isinstance(merged, dict)
    permissions = merged.get("permissions")
    assert isinstance(permissions, dict)
    assert permissions.get("spawn_subagent") == "allow"
    assert permissions.get("invoke_external_agent") == "deny"


def _delegate_stream_started(events: list[dict[str, object]]) -> bool:
    for event in events:
        try:
            raw = json.dumps(event)
        except TypeError:
            continue
        if "delegate:" in raw or "delegation_" in raw:
            return True
    return False


def _stream_error_text(events: list[dict[str, object]]) -> str:
    chunks: list[str] = []
    for event in events:
        if event.get("type") != "error":
            continue
        data = event.get("data")
        if isinstance(data, str) and data:
            chunks.append(data)
    return " ".join(chunks)


@pytest.mark.e2e
def test_readonly_security_config_spawn_allow_invoke_deny_engine() -> None:
    """DPSEAG: readonly profile allows internal spawn but denies external CLI."""
    from myrm_agent_harness.agent.security.engine import evaluate_tool_call
    from myrm_agent_harness.agent.security.types import PermissionAction, SecurityConfig

    config = SecurityConfig.readonly()
    spawn_action, _ = evaluate_tool_call("spawn_subagent", {}, config)
    external_action, _ = evaluate_tool_call(
        "invoke_external_agent",
        {"agent": "echo-cli"},
        config,
    )
    assert spawn_action == PermissionAction.ALLOW
    assert external_action == PermissionAction.DENY


@pytest.mark.e2e
@patch(
    "app.ai_agents.general_agent.external_agents._resolve_external_agent_cfgs",
    new=AsyncMock(return_value=[{"name": "echo-cli", "type": "cli", "command": "echo", "args": []}]),
)
def test_workspace_security_config_blocks_force_external_on_ask(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Lane-C: workspace invoke_external_agent=ASK must block direct force_external routing."""
    from tests.api.agent.conftest import _build_mock_user_configs

    configs = _build_mock_user_configs()
    configs.security_config_dict = {
        "capabilities": [{"permission": "*", "pattern": "*"}],
        "permissions": {
            "spawn_subagent": "allow",
            "invoke_external_agent": "ask",
            "file_write": "ask",
            "shell_exec": "ask",
        },
        "yoloModeEnabled": False,
        "autoModeEnabled": False,
    }
    mock_load_user_configs.return_value = configs

    chat_id = f"test_workspace_ext_block_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Run external CLI task",
        "message_id": f"msg-{chat_id}",
        "chat_id": chat_id,
        "action_mode": "agent",
        "force_external_agent": "echo-cli",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["external_cli"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    error_text = _stream_error_text(events).lower()
    assert "external agent delegation denied" in error_text, events
    assert "ask" in error_text or "denied" in error_text
    assert not _delegate_stream_started(events), events


@pytest.mark.e2e
@patch(
    "app.ai_agents.general_agent.external_agents._resolve_external_agent_cfgs",
    new=AsyncMock(return_value=[{"name": "echo-cli", "type": "cli", "command": "echo", "args": []}]),
)
def test_readonly_security_config_blocks_force_external_delegate_stream(
    client: TestClient,
    mock_load_user_configs: AsyncMock,
) -> None:
    """Lane-C: builtin readonly profile must block force_external_agent direct routing."""
    from tests.api.agent.conftest import _build_mock_user_configs

    configs = _build_mock_user_configs()
    configs.security_config_dict = {
        "capabilities": [{"permission": "*", "pattern": "*"}],
        "permissions": {
            "spawn_subagent": "allow",
            "invoke_external_agent": "deny",
            "file_write": "deny",
            "shell_exec": "deny",
        },
        "yoloModeEnabled": False,
        "autoModeEnabled": False,
    }
    mock_load_user_configs.return_value = configs

    chat_id = f"test_readonly_ext_block_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Run external CLI task",
        "message_id": f"msg-{chat_id}",
        "chat_id": chat_id,
        "action_mode": "agent",
        "force_external_agent": "echo-cli",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["external_cli"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    error_text = _stream_error_text(events).lower()
    assert "external agent delegation denied" in error_text, events
    assert not _delegate_stream_started(events), events


@pytest.mark.e2e
@patch(
    "app.ai_agents.general_agent.external_agents._resolve_external_agent_cfgs",
    new=AsyncMock(return_value=[{"name": "echo-cli", "type": "cli", "command": "echo", "args": []}]),
)
def test_explore_preset_blocks_force_external_delegate_stream(
    client: TestClient,
) -> None:
    """Lane-C: explore preset deny invoke_external_agent must block force_external_agent path."""
    chat_id = f"test_explore_ext_block_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Run external CLI task",
        "message_id": f"msg-{chat_id}",
        "chat_id": chat_id,
        "action_mode": "agent",
        "security_preset": "explore",
        "force_external_agent": "echo-cli",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["external_cli"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    error_text = _stream_error_text(events).lower()
    assert "external agent delegation denied" in error_text, events
    assert "invoke_external_agent" in error_text or "denied" in error_text
    assert not _delegate_stream_started(events), events


@pytest.mark.e2e
def test_agent_stream_external_cli_on_skips_delegate_without_backends(
    client: TestClient,
) -> None:
    """external_cli ON alone must not mount delegate when no CLI backends resolve."""
    chat_id = f"test_ext_cli_no_backend_{uuid.uuid4().hex[:8]}"
    with patch(
        "app.ai_agents.general_agent.external_agents._resolve_external_agent_cfgs",
        new=AsyncMock(return_value=None),
    ):
        events = _collect_agent_stream(client, _external_cli_payload(chat_id, include_external_cli=True))
    check_e2e_errors(events)

    tool_names = _tool_names_from_snapshot(events)
    if tool_names:
        assert "invoke_acp_agent_tool" not in tool_names
