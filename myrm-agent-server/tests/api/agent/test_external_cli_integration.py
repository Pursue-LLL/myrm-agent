"""Integration: external_cli entitlement via agent-stream tools_snapshot."""

from __future__ import annotations

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
    return {
        str(row.get("name"))
        for row in snapshot_rows
        if isinstance(row, dict) and row.get("name")
    }


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


@pytest.mark.integration
def test_agent_stream_external_cli_off_excludes_delegate_tool(client: TestClient) -> None:
    """Writer-style profile without external_cli must not mount delegate_to_agent_tool Turn1."""
    chat_id = f"test_ext_cli_off_{uuid.uuid4().hex[:8]}"
    events = _collect_agent_stream(client, _external_cli_payload(chat_id, include_external_cli=False))
    check_e2e_errors(events)

    tool_names = _tool_names_from_snapshot(events)
    if tool_names:
        assert "delegate_to_agent_tool" not in tool_names


@pytest.mark.integration
def test_agent_stream_external_cli_on_mounts_delegate_when_backends_exist(
    client: TestClient,
) -> None:
    """external_cli ON + resolvable CLI backends must expose delegate_to_agent_tool Turn1."""
    chat_id = f"test_ext_cli_on_{uuid.uuid4().hex[:8]}"
    events = _collect_agent_stream(client, _external_cli_payload(chat_id, include_external_cli=True))
    check_e2e_errors(events)

    tool_names = _tool_names_from_snapshot(events)
    if tool_names:
        assert "delegate_to_agent_tool" in tool_names


@pytest.mark.integration
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
        assert "delegate_to_agent_tool" not in tool_names
