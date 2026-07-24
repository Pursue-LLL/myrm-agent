import uuid
from contextlib import asynccontextmanager

import pytest
from fastapi.testclient import TestClient

from app.core.channel_bridge.topic_config import (
    SEARCH_AGENT_CHANNEL_BIND_MSG,
    _CHANNEL_LEVEL_KEY,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app("user_agents", preset="channels_local")


async def _ensure_builtin_agents_seeded() -> None:
    from app.services.agent.builtin_initializer import initialize_builtin_agents

    await initialize_builtin_agents()


async def _seed_legacy_search_global_bind(channel: str) -> None:
    from app.core.channel_bridge.topic_config import SqlTopicManager

    manager = SqlTopicManager()
    await manager._save_config(
        channel,
        {
            "__global__": {
                _CHANNEL_LEVEL_KEY: {
                    "agentId": "builtin-fast-search",
                    "enabled": True,
                    "boundAt": "2020-01-01T00:00:00+00:00",
                }
            }
        },
    )


@asynccontextmanager
async def _db_lifespan(app):
    from app.database.connection import init_database

    await init_database()
    yield


@pytest.fixture
def client():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _db_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.router.lifespan_context = original_lifespan


def test_topic_binding_e2e(client):
    """End-to-end test for channel topic binding without mocks."""

    unique_id = str(uuid.uuid4())[:8]

    # 0. Create an agent
    agent_payload = {
        "name": f"E2E Test Agent {unique_id}",
        "description": "Agent for E2E testing",
        "model": "gpt-4o",
        "systemPrompt": "You are a helpful assistant.",
        "skills": [],
    }
    res = client.post("/api/v1/user-agents", json=agent_payload)
    assert res.status_code == 200, res.text
    agent_id = res.json()["data"]["id"]

    channel_name = f"test_e2e_channel_{unique_id}"
    topic_id = f"test_e2e_chat_{unique_id}:test_e2e_thread_{unique_id}"

    # 1. Bind an agent to a topic
    bind_payload = {
        "agentId": agent_id,
        "displayName": "E2E Test Group",
        "avatarUrl": "http://example.com/e2e.png",
    }

    response = client.post(
        f"/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        json=bind_payload,
    )
    assert response.status_code == 200, response.text

    # 2. Get topics to verify
    response = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    assert response.status_code == 200, response.text
    data = response.json()

    # Find the topic
    topics = data["topics"]
    found = False
    for t in topics:
        if t["topicId"] == topic_id:
            assert t["agentId"] == agent_id
            assert t["displayName"] == "E2E Test Group"
            assert t["avatarUrl"] == "http://example.com/e2e.png"
            assert t["threadSharingMode"] == "isolated"  # Default value
            found = True
    assert found, "Topic not found in list"

    # 3. Set global default agent
    global_payload = {"agentId": agent_id}
    response = client.post(
        f"/api/v1/channels/manage/{channel_name}/default-agent", json=global_payload
    )
    assert response.status_code == 200, response.text

    # 4. Verify global default agent
    response = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    data = response.json()
    assert data["globalAgentId"] == agent_id

    # 5. Unbind agent
    unbind_payload = {
        "agentId": None,
        "displayName": "E2E Test Group Unbound",
        "avatarUrl": "http://example.com/e2e.png",
    }
    response = client.post(
        f"/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        json=unbind_payload,
    )
    assert response.status_code == 200, response.text

    # Verify unbind
    response = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    data = response.json()
    topics = data["topics"]
    for t in topics:
        if t["topicId"] == topic_id:
            assert t["agentId"] is None
            assert t["displayName"] == "E2E Test Group Unbound"

    # 6. Bind invalid agent
    invalid_payload = {
        "agentId": "invalid-uuid",
        "displayName": "E2E Test Group Invalid",
        "avatarUrl": "http://example.com/e2e.png",
    }
    response = client.post(
        f"/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        json=invalid_payload,
    )
    assert response.status_code == 404, response.text

    print("E2E Test Passed Successfully (Including Edge Cases)!")


def test_search_agent_channel_bind_rejected_e2e(client):
    """Real DB: Search-track agents cannot bind to channels; legacy binds are purged on read."""
    import asyncio

    asyncio.run(_ensure_builtin_agents_seeded())

    unique_id = str(uuid.uuid4())[:8]
    channel_name = f"test_search_reject_{unique_id}"
    topic_id = f"chat_{unique_id}:thread_{unique_id}"

    default_response = client.post(
        f"/api/v1/channels/manage/{channel_name}/default-agent",
        json={"agentId": "builtin-fast-search"},
    )
    assert default_response.status_code == 400, default_response.text
    assert SEARCH_AGENT_CHANNEL_BIND_MSG in default_response.json()["detail"]

    topics_response = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    assert topics_response.status_code == 200, topics_response.text
    assert topics_response.json()["globalAgentId"] is None

    topic_response = client.post(
        f"/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        json={"agentId": "builtin-fast-search"},
    )
    assert topic_response.status_code == 400, topic_response.text
    assert SEARCH_AGENT_CHANNEL_BIND_MSG in topic_response.json()["detail"]

    asyncio.run(_seed_legacy_search_global_bind(channel_name))
    sanitized = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    assert sanitized.status_code == 200, sanitized.text
    assert sanitized.json()["globalAgentId"] is None


def test_topic_thread_sharing_mode_e2e(client):
    """End-to-end test for thread sharing mode configuration."""

    unique_id = str(uuid.uuid4())[:8]

    # Create an agent
    agent_payload = {
        "name": f"E2E Sharing Agent {unique_id}",
        "description": "Agent for thread sharing testing",
        "model": "gpt-4o",
        "systemPrompt": "You are a collaborative assistant.",
        "skills": [],
    }
    res = client.post("/api/v1/user-agents", json=agent_payload)
    assert res.status_code == 200, res.text
    agent_id = res.json()["data"]["id"]

    channel_name = f"test_sharing_channel_{unique_id}"
    topic_id = f"test_forum_{unique_id}:test_thread_{unique_id}"

    # 1. Bind with shared mode
    bind_shared_payload = {
        "agentId": agent_id,
        "displayName": "Shared Forum Topic",
        "avatarUrl": "http://example.com/shared.png",
        "threadSharingMode": "shared",
    }

    response = client.post(
        f"/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        json=bind_shared_payload,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["threadSharingMode"] == "shared"

    # 2. Verify shared mode in topics list
    response = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    assert response.status_code == 200, response.text
    data = response.json()

    found = False
    for t in data["topics"]:
        if t["topicId"] == topic_id:
            assert t["threadSharingMode"] == "shared"
            found = True
    assert found, "Topic with shared mode not found"

    # 3. Update to isolated mode
    bind_isolated_payload = {"agentId": agent_id, "threadSharingMode": "isolated"}

    response = client.post(
        f"/api/v1/channels/manage/{channel_name}/topics/{topic_id}/bind",
        json=bind_isolated_payload,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["threadSharingMode"] == "isolated"

    # 4. Verify isolated mode
    response = client.get(f"/api/v1/channels/manage/{channel_name}/topics")
    data = response.json()

    for t in data["topics"]:
        if t["topicId"] == topic_id:
            assert t["threadSharingMode"] == "isolated"

    print("Thread Sharing Mode E2E Test Passed!")
