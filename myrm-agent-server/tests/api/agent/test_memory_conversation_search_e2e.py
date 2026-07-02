"""Memory + conversation_search deferred API integration tests (no mock on agent-stream path)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_model_selection


def _collect_agent_stream(client: TestClient, payload: dict[str, object]) -> list[dict[str, object]]:
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


def _stream_blob(events: list[dict[str, object]]) -> str:
    return json.dumps(events, ensure_ascii=False, default=str)


def _invoked_tool_names(events: list[dict[str, object]]) -> set[str]:
    """Tool names from execution events only (not schema/discover metadata in stream)."""
    names: set[str] = set()
    for event in events:
        if not isinstance(event, dict):
            continue
        event_type = event.get("type")
        if event_type not in {"tasks_steps", "tool_end", "tool_start"}:
            continue
        tool_name = event.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            names.add(tool_name)
    return names


@pytest.mark.integration
def test_agent_stream_enable_memory_completes(client: TestClient) -> None:
    """Full agent-stream with enable_memory must complete without error."""
    payload = {
        "query": "Say hello in one short sentence.",
        "message_id": "test-memory-e2e-hello",
        "chat_id": "test_memory_e2e_hello",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "enable_memory": True,
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    assert events, "expected at least one SSE event"


@pytest.mark.integration
def test_agent_stream_incognito_still_allows_recall_tools(client: TestClient) -> None:
    """Incognito + memory: save/manage absent; stream still succeeds with deferred conversation_search wired."""
    payload = {
        "query": "What is 2+2? Answer briefly.",
        "message_id": "test-memory-e2e-incognito",
        "chat_id": "test_memory_e2e_incognito",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "enable_memory": True,
        "incognito_mode": True,
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    blob = _stream_blob(events)
    assert "memory_save_tool" not in blob
    assert "memory_manage_tool" not in blob


@pytest.mark.integration
def test_agent_stream_enable_memory_false_skips_memory_and_conversation_search(client: TestClient) -> None:
    """enable_memory=false: no memory tools and no conversation_search invocation."""
    payload = {
        "query": "Reply with the word OK only.",
        "message_id": "test-memory-e2e-disabled",
        "chat_id": "test_memory_e2e_disabled",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "enable_memory": False,
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    invoked = _invoked_tool_names(events)
    assert not invoked & {
        "memory_recall_tool",
        "memory_save_tool",
        "memory_manage_tool",
        "conversation_search_tool",
    }, f"memory off should not invoke memory/conversation tools; invoked={sorted(invoked)}"


@pytest.mark.integration
def test_agent_stream_simple_query_does_not_invoke_conversation_search(client: TestClient) -> None:
    """Turn1 trivial query should not call conversation_search (deferred + L2 path)."""
    payload = {
        "query": "Reply with the word OK only.",
        "message_id": "test-memory-e2e-no-conv-search",
        "chat_id": "test_memory_e2e_no_conv_search",
        "action_mode": "agent",
        "model_selection": get_model_selection(),
        "enable_memory": True,
        "timezone": "UTC",
    }
    events = _collect_agent_stream(client, payload)
    check_e2e_errors(events)
    invoked = _invoked_tool_names(events)
    assert "conversation_search_tool" not in invoked, (
        f"conversation_search should stay deferred on trivial turn1; invoked={sorted(invoked)}"
    )


@pytest.mark.integration
def test_agent_stream_multi_turn_continue_topic(client: TestClient) -> None:
    """Two-turn chat: continue prior topic should complete (L2 / memory path)."""
    model_selection = get_model_selection()
    chat_id = "test_memory_e2e_multi_turn"

    turn1 = {
        "query": "Remember for this chat: our codename is BLUEFISH.",
        "message_id": "test-memory-mt-1",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": model_selection,
        "enable_memory": True,
        "timezone": "UTC",
    }
    events1 = _collect_agent_stream(client, turn1)
    check_e2e_errors(events1)

    turn2 = {
        "query": "What was our codename in this conversation?",
        "message_id": "test-memory-mt-2",
        "chat_id": chat_id,
        "action_mode": "agent",
        "model_selection": model_selection,
        "enable_memory": True,
        "timezone": "UTC",
        "chat_history": [
            {"role": "user", "content": turn1["query"]},
            {"role": "assistant", "content": "Noted, codename BLUEFISH."},
        ],
    }
    events2 = _collect_agent_stream(client, turn2)
    check_e2e_errors(events2)
    blob2 = _stream_blob(events2)
    assert "BLUEFISH" in blob2.upper() or "bluefish" in blob2.lower()
