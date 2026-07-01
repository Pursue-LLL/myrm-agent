"""Agent-stream E2E: llm_map_tool registration and invocation via real LLM.

Note: in-process TestClient agent-stream may skip when the local LLM checkpoint hits
``msgpack serializable: function`` (same as test_code_execution_e2e). Real tool + engine
coverage lives in tests/integration/test_llm_map_integration.py.
"""

from __future__ import annotations

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.api.agent.utils import check_e2e_errors, get_lite_model_selection, get_model_selection

E2E_PROMPT = (
    "E2E_LLM_MAP_RUN: You MUST call llm_map_tool exactly once with:\n"
    '- instruction: "Reply with only the word OK"\n'
    '- items: ["alpha", "beta", "gamma"]\n'
    "- max_concurrency: 2\n"
    "Do not use any other tool. After the tool returns, reply with one sentence summarising "
    "how many items succeeded according to the tool summary."
)


def _stream_model_selection() -> dict[str, object]:
    """Prefer lite model for stream tests — avoids thinking-kwargs checkpoint issues."""
    return dict(get_lite_model_selection())


def _collect_agent_stream(
    client: TestClient,
    query: str,
    *,
    enabled_tools: list[str],
    use_lite: bool = True,
) -> tuple[str, list[dict[str, object]], list[str]]:
    chat_id = f"llm-map-{uuid.uuid4().hex[:10]}"
    request_data: dict[str, object] = {
        "messageId": f"llm-map-msg-{uuid.uuid4().hex[:12]}",
        "chatId": chat_id,
        "query": query,
        "modelSelection": _stream_model_selection(),
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
        "agentConfig": {
            "skill_ids": [],
            "enabled_builtin_tools": enabled_tools,
        },
        "securityOverrides": {"yoloModeEnabled": True},
    }
    if use_lite:
        request_data["liteModelSelection"] = get_lite_model_selection()

    collected: list[dict[str, object]] = []
    message_chunks: list[str] = []
    tool_names: list[str] = []

    with client.stream("POST", "/api/v1/agents/agent-stream", json=request_data, timeout=300.0) as response:
        assert response.status_code == 200, response.text
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            collected.append(event)
            event_type = event.get("type")
            if event_type in ("message", "reasoning"):
                chunk = event.get("data", "")
                if isinstance(chunk, str) and chunk:
                    message_chunks.append(chunk)
            elif event_type == "tasks_steps":
                tool_name = event.get("tool_name")
                if isinstance(tool_name, str) and tool_name:
                    tool_names.append(tool_name)

    return "".join(message_chunks), collected, tool_names


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E requires BASIC_API_KEY in .env.test",
)
class TestLlmMapAgentStreamE2E:
    """Full server path: agent-stream → harness → llm_map_tool."""

    def test_llm_map_tool_invoked_when_enabled(self, client: TestClient) -> None:
        message, collected, tool_names = _collect_agent_stream(
            client,
            E2E_PROMPT,
            enabled_tools=["llm_map", "answer_tool"],
        )
        assert collected, "Expected SSE events"
        check_e2e_errors(collected)

        assert "llm_map_tool" in tool_names, (
            f"Expected llm_map_tool in stream tools, got {tool_names!r}; message={message[:400]!r}"
        )

    def test_llm_map_disabled_skips_tool(self, client: TestClient) -> None:
        _, collected, tool_names = _collect_agent_stream(
            client,
            E2E_PROMPT,
            enabled_tools=["answer_tool"],
        )
        assert collected
        check_e2e_errors(collected)
        assert "llm_map_tool" not in tool_names
