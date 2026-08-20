"""Integration: agent-stream tools_snapshot emits semantic ToolLayer slugs."""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import get_lite_model_selection

_VALID_LAYER_SLUGS = frozenset({"core", "common", "extended", "external"})


def _collect_until(
    client: TestClient,
    payload: dict[str, object],
    stop_when: Callable[[dict[str, object], list[dict[str, object]]], bool],
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    with client.stream(
        "POST",
        "/api/v1/agents/agent-stream",
        json=payload,
        timeout=120.0,
    ) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            raw = line.strip()[6:]
            if raw == "[DONE]":
                break
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                collected.append(data)
                if stop_when(data, collected):
                    break
    return collected


def _stop_on_tools_snapshot(
    event: dict[str, object],
    _collected: list[dict[str, object]],
) -> bool:
    return event.get("type") == "tools_snapshot"


@pytest.mark.e2e
@pytest.mark.timeout(180)
def test_agent_stream_tools_snapshot_semantic_layer_slugs(
    client: TestClient,
) -> None:
    """Turn1 tools_snapshot rows use core/common/extended/external slugs (not digits)."""
    chat_id = f"test_layer_slug_{uuid.uuid4().hex[:8]}"
    payload: dict[str, object] = {
        "query": "Reply OK.",
        "message_id": "test-layer-slug-1",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": get_lite_model_selection(),
        "agent_config": {
            "enabled_builtin_tools": ["web_search", "memory", "image_generation"],
            "skill_ids": [],
        },
        "timezone": "UTC",
    }
    events = _collect_until(client, payload, _stop_on_tools_snapshot)
    tools_snapshot = next(
        (event for event in events if event.get("type") == "tools_snapshot"),
        None,
    )
    assert tools_snapshot is not None, "expected tools_snapshot in agent-stream"

    snapshot_rows = tools_snapshot.get("data")
    assert isinstance(snapshot_rows, list), "tools_snapshot data must be a list"
    assert snapshot_rows, "tools_snapshot must not be empty"

    by_name = {row["name"]: row for row in snapshot_rows if isinstance(row, dict) and isinstance(row.get("name"), str)}
    assert "web_search_tool" in by_name, "web_search_tool must be Turn1 bound"
    assert by_name["web_search_tool"].get("layer") == "common"
    assert "bash_code_execute_tool" in by_name
    assert by_name["bash_code_execute_tool"].get("layer") == "core"

    if "image_tool" in by_name:
        assert by_name["image_tool"].get("layer") == "external"

    for row in snapshot_rows:
        if not isinstance(row, dict):
            continue
        layer = row.get("layer")
        assert isinstance(layer, str), f"layer must be str for {row.get('name')}"
        assert layer in _VALID_LAYER_SLUGS, f"unexpected layer slug {layer!r}"
