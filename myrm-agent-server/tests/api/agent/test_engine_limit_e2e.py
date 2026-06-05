"""Engine Limit E2E Test.

Test that engine limits (e.g. max_tool_calls) trigger ENGINE_LIMIT_REACHED events.
"""

import json
import os
import uuid

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from tests.api.agent.utils import get_model_selection, get_search_service_config


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
        # 1. Create an agent with max_tool_calls = 1
        create_payload = {
            "name": "Limit Test Agent",
            "description": "Test max_tool_calls",
            "system_prompt": "You are a helpful assistant.",
            "is_built_in": False,
            "skill_ids": [],
            "mcp_ids": [],
            "engine_params": {"max_tool_calls": 1},
        }

        response = await async_client.post("/api/agents", json=create_payload)
        assert response.status_code == 200
        created_agent = response.json()["data"]
        agent_id = created_agent["id"]

        try:
            # 2. Run a query that requires multiple tool calls
            # We use ast_search_tool because it doesn't require approval and won't suspend the agent
            query = "Use the ast_search_tool to search for 'Foo'. Then use it again to search for 'Bar'. Then use it again to search for 'Baz'."

            chat_id = str(uuid.uuid4())
            message_id = str(uuid.uuid4())

            search_request = {
                "messageId": message_id,
                "chatId": chat_id,
                "agent_id": agent_id,
                "query": query,
                "modelSelection": get_model_selection(),
                "searchServiceCfg": get_search_service_config(),
                "actionMode": "agent",
            }

            collected_data = []
            limit_reached_event = None
            approval_required = False

            with client.stream("POST", "/api/v1/agents/agent-stream", json=search_request) as stream_response:
                for line in stream_response.iter_lines():
                    if line and line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])
                            if data is None:
                                continue
                            collected_data.append(data)
                            if data.get("type") == "engine_limit_reached":
                                limit_reached_event = data
                                break
                            if data.get("type") in (
                                "approval_required",
                                "tool_approval_request",
                            ):
                                approval_required = True
                        except json.JSONDecodeError:
                            pass

            if approval_required:
                print("\n🔧 Auto-approving tool call...")
                resume_request = search_request.copy()
                resume_request["resumeValue"] = [{"type": "approve", "extensions": {"allowAlways": True}}]
                with client.stream("POST", "/api/v1/agents/agent-stream", json=resume_request) as stream_response:
                    for line in stream_response.iter_lines():
                        if line and line.startswith("data: "):
                            try:
                                data = json.loads(line[6:])
                                if data is None:
                                    continue
                                collected_data.append(data)
                                if data.get("type") == "engine_limit_reached":
                                    limit_reached_event = data
                                    break
                            except json.JSONDecodeError:
                                pass

            # Verify the event was emitted
            assert limit_reached_event is not None, "ENGINE_LIMIT_REACHED event should be emitted"
            assert limit_reached_event["data"]["limit_type"] == "max_tool_calls"

            print("\n✅ Test Passed: max_tool_calls limit triggered ENGINE_LIMIT_REACHED")

        finally:
            # Cleanup
            await async_client.delete(f"/api/agents/{agent_id}")
