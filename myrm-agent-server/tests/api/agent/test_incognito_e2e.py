"""Incognito mode E2E: session must not read or write memory."""

import json

from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection

_MEMORY_TOOL_NAMES = frozenset(
    {
        "memory_search_tool",
        "memory_save_tool",
        "memory_manage_tool",
        "conversation_search_tool",
    }
)
_MEMORY_CONTEXT_MARKERS = frozenset(
    {
        "<user_memory_context",
        "<<<UNTRUSTED_DATA",
    }
)


def _collect_stream(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line and line.strip().startswith("data: "):
                try:
                    data = json.loads(line.strip()[6:])
                    if isinstance(data, dict):
                        collected.append(data)
                except json.JSONDecodeError:
                    pass
    return collected


def _assert_incognito_memory_absent(blob: str) -> None:
    for tool_name in _MEMORY_TOOL_NAMES:
        assert tool_name not in blob, f"{tool_name} must not appear in incognito stream"
    for marker in _MEMORY_CONTEXT_MARKERS:
        assert marker not in blob, f"{marker} must not appear in incognito stream"


def test_incognito_mode_stream(client: TestClient):
    """Basic incognito stream must return 200 and complete without errors."""
    events = _collect_stream(
        client,
        {
            "query": "hello incognito",
            "message_id": "test-msg-id",
            "chat_id": "test_incognito_e2e",
            "action_mode": "fast",
            "search_depth": "normal",
            "model_selection": get_model_selection(),
            "enable_memory": True,
            "incognito_mode": True,
            "timezone": "UTC",
        },
    )
    check_e2e_errors(events)


def test_incognito_excludes_all_memory_tools_and_context(client: TestClient):
    """Incognito must not bind or inject any memory or conversation_search surface."""
    events = _collect_stream(
        client,
        {
            "query": "Remember that my favorite color is blue",
            "message_id": "test-msg-incognito-no-memory",
            "chat_id": "test_incognito_no_memory",
            "action_mode": "agent",
            "model_selection": get_model_selection(),
            "enable_memory": True,
            "enable_conversation_search": True,
            "incognito_mode": True,
            "timezone": "UTC",
        },
    )
    check_e2e_errors(events)
    blob = json.dumps(events, ensure_ascii=False, default=str)
    _assert_incognito_memory_absent(blob)
