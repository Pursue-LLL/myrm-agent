"""Engine Limit E2E Test.

Test that engine limits (e.g. max_tool_calls) trigger ENGINE_LIMIT_REACHED events.
"""

from __future__ import annotations

import json
import os
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from tests.api.agent.utils import get_model_selection, get_search_service_config


def _extract_engine_limit_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Find engine_limit_reached in SSE payloads (direct or via tasks_steps error)."""
    for data in events:
        if data.get("type") == "engine_limit_reached":
            return data
        if data.get("type") == "tasks_steps" and data.get("status") == "error":
            error_text = str(data.get("error") or "")
            if "Tool call limit exceeded" in error_text:
                return {
                    "type": "engine_limit_reached",
                    "data": {
                        "limit_type": "max_tool_calls",
                        "tool_name": data.get("tool_name"),
                        "message": error_text,
                    },
                }
    return None


def _consume_agent_stream(client: TestClient, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], bool]:
    collected: list[dict[str, Any]] = []
    approval_required = False
    with client.stream("POST", "/api/v1/agents/agent-stream", json=payload) as stream_response:
        for line in stream_response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            try:
                data = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if data is None:
                continue
            collected.append(data)
            if data.get("type") in ("approval_required", "tool_approval_request"):
                approval_required = True
            if data.get("type") in ("engine_limit_reached", "message_end", "error"):
                break
    return collected, approval_required


@pytest.fixture
async def async_client(app):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestEngineLimitE2E:
    """End-to-End tests for Engine Limits."""

    async def test_max_tool_calls_limit(self, async_client: AsyncClient, client: TestClient):
        """Test that max_tool_calls limit triggers ENGINE_LIMIT_REACHED."""
        create_payload = {
            "name": "Limit Test Agent",
            "description": "Test max_tool_calls",
            "system_prompt": (
                "You are a helpful assistant. When asked to search, call grep_tool sequentially: "
                "one call per step, wait for each result before the next call."
            ),
            "is_built_in": False,
            "skill_ids": [],
            "mcp_ids": [],
            "enabled_builtin_tools": ["web_search", "memory", "file_ops", "code_execute"],
            "engine_params": {
                "max_tool_calls": 1,
                "enable_parallel_tool_calls": False,
            },
        }

        response = await async_client.post("/api/agents", json=create_payload)
        assert response.status_code == 200
        created_agent = response.json()["data"]
        agent_id = created_agent["id"]

        try:
            query = (
                "Step 1: use grep_tool to search for 'Foo'. "
                "Step 2: use grep_tool again to search for 'Bar'. "
                "Step 3: use grep_tool again to search for 'Baz'. "
                "Report how many grep calls succeeded."
            )

            search_request = {
                "messageId": str(uuid.uuid4()),
                "chatId": str(uuid.uuid4()),
                "agent_id": agent_id,
                "query": query,
                "modelSelection": get_model_selection(),
                "searchServiceCfg": get_search_service_config(),
                "actionMode": "agent",
            }

            collected_data, approval_required = _consume_agent_stream(client, search_request)

            if approval_required:
                resume_request = search_request.copy()
                resume_request["resumeValue"] = [{"type": "approve", "extensions": {"allowAlways": True}}]
                resume_collected, _ = _consume_agent_stream(client, resume_request)
                collected_data.extend(resume_collected)

            limit_reached_event = _extract_engine_limit_event(collected_data)
            assert limit_reached_event is not None, (
                "ENGINE_LIMIT_REACHED event should be emitted; "
                f"got event types: {[d.get('type') for d in collected_data]}"
            )
            assert limit_reached_event["data"]["limit_type"] == "max_tool_calls"

        finally:
            await async_client.delete(f"/api/agents/{agent_id}")
