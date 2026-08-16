"""API integration: agent-stream on unsupported allowed_tools gateways (minimax/agnes-class)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection

_FORBIDDEN_STREAM_MARKERS: tuple[str, ...] = (
    "invalid tool choice",
    "allowed_tools",
    "tool_choice.type",
    "unsupported tool_choice",
)


def _collect_agent_stream(
    client: TestClient, payload: dict[str, object]
) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.strip().startswith("data: "):
                continue
            try:
                data = json.loads(line.strip()[6:])
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                collected.append(data)
    return collected


def _assert_no_allowed_tools_gateway_error(events: list[dict[str, object]]) -> None:
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("type") != "error":
            continue
        error_msg = str(event.get("error", "") or event.get("data", "")).lower()
        for marker in _FORBIDDEN_STREAM_MARKERS:
            assert (
                marker not in error_msg
            ), f"agent-stream error must not be allowed_tools gateway rejection: {error_msg[:200]!r}"


@pytest.mark.e2e
def test_agent_stream_minimax_no_allowed_tools_gateway_error(
    client: TestClient,
) -> None:
    """Real agent-stream with minimax must complete without allowed_tools HTTP 400."""
    payload = {
        "query": "Reply with exactly: ALLOWED_TOOLS_OK",
        "message_id": "test-allowed-tools-stream-ok",
        "chat_id": "test_allowed_tools_stream_ok",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "enable_memory": False,
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    _assert_no_allowed_tools_gateway_error(events)
    assert events, "expected at least one SSE event"


@pytest.mark.e2e
def test_agent_stream_readonly_intent_no_allowed_tools_gateway_error(
    client: TestClient,
) -> None:
    """Readonly intent turn policy must not trigger allowed_tools gateway rejection."""
    payload = {
        "query": "请分析这段日志为什么会失败？不要修改任何文件，只解释原因。",
        "message_id": "test-allowed-tools-readonly",
        "chat_id": "test_allowed_tools_readonly",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "enable_memory": False,
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    _assert_no_allowed_tools_gateway_error(events)
    assert events, "expected at least one SSE event"
