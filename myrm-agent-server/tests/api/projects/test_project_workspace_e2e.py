import json
import os
from typing import Optional

import pytest
import httpx
from httpx import ASGITransport
from app.main import app

@pytest.fixture
async def async_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
        timeout=60.0,
    ) as client:
        yield client

from tests.api.agent.utils import (
    check_e2e_errors,
    get_model_selection,
)

@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="E2E test requires BASIC_API_KEY environment variable",
)
class TestProjectWorkspaceE2E:
    """Project Workspace & Multi-Agent Collaboration E2E Tests"""

    @pytest.mark.asyncio
    async def test_project_workspace_agent_routing(self, async_client: httpx.AsyncClient):
        # 1. Create a project
        project_resp = await async_client.post("/api/v1/projects/", json={"name": "E2E Project Workspace"})
        assert project_resp.status_code == 200
        project_id = project_resp.json()["data"]["project"]["id"]
        workspace_path = project_resp.json()["data"]["project"].get("workspacePath")

        # 2. Create a chat and assign it to the project
        chat_id = "c-test-proj-e2e"
        await async_client.post(f"/api/v1/chats/", json={"id": chat_id, "title": "E2E Chat"})
        await async_client.patch(f"/api/v1/projects/chats/{chat_id}/project", json={"projectId": project_id})

        # 3. Send a message referencing an agent
        model_selection = get_model_selection()
        search_request = {
            "query": "Hello, @builtin-fast-search please tell me what is 1+1?",
            "message_id": "test-msg-id-1",
            "chat_id": chat_id,
            "action_mode": "chat",
            "mentioned_agent_ids": ["builtin-fast-search"],
            "model_selection": model_selection,
            "timezone": "UTC",
        }

        collected_data = []
        message_chunks = []
        
        async with async_client.stream(
            "POST", "/api/v1/agents/agent-stream", json=search_request
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if not isinstance(data, dict):
                        continue
                    collected_data.append(data)
                    event_type = data.get("type", "unknown")
                    if event_type == "message":
                        content = data.get("data", "")
                        if content:
                            message_chunks.append(content)
                except json.JSONDecodeError:
                    pass

        check_e2e_errors(collected_data)
        has_message_end = any(d.get("type") == "message_end" for d in collected_data)
        assert has_message_end, "Should have message_end event"
        
        # Clean up
        await async_client.delete(f"/api/v1/projects/{project_id}")
