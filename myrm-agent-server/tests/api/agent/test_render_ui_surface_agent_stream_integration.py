"""Integration: agent-stream tools_snapshot respects render_ui surface mount gate."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.test_capability_gap_integration import _collect_agent_stream
from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection

_AGENT_STREAM_TEST_TIMEOUT = pytest.mark.timeout(420)


def _snapshot_tool_names(events: list[dict[str, object]]) -> set[str]:
    tools_snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
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


def _base_payload(*, client_surface: str | None) -> dict[str, object]:
    chat_id = f"test_render_ui_surface_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Reply with the word OK only.",
        "message_id": f"msg_{uuid.uuid4().hex[:8]}",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["render_ui", "web_search"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    if client_surface is not None:
        payload["client_surface"] = client_surface
    return payload


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_web_surface_mounts_render_ui_tools(client: TestClient) -> None:
    events = _collect_agent_stream(client, _base_payload(client_surface="web"))
    check_e2e_errors(events)

    tool_names = _snapshot_tool_names(events)
    if not tool_names:
        pytest.skip("tools_snapshot not emitted in this stream")

    assert "render_ui_tool" in tool_names
    assert "update_ui_data_tool" in tool_names


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_headless_surface_omits_render_ui_tools(client: TestClient) -> None:
    events = _collect_agent_stream(client, _base_payload(client_surface="headless"))
    check_e2e_errors(events)

    tool_names = _snapshot_tool_names(events)
    if not tool_names:
        pytest.skip("tools_snapshot not emitted in this stream")

    assert "render_ui_tool" not in tool_names
    assert "update_ui_data_tool" not in tool_names


@pytest.mark.integration
@_AGENT_STREAM_TEST_TIMEOUT
def test_agent_stream_tauri_surface_mounts_render_ui_tools(client: TestClient) -> None:
    events = _collect_agent_stream(client, _base_payload(client_surface="tauri"))
    check_e2e_errors(events)

    tool_names = _snapshot_tool_names(events)
    if not tool_names:
        pytest.skip("tools_snapshot not emitted in this stream")

    assert "render_ui_tool" in tool_names
    assert "update_ui_data_tool" in tool_names
