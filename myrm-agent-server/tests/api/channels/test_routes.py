from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.channels.types import TopicContext
from app.main import app


async def override_get_deploy_identity():
    return "test_user_id"


async def override_get_db():
    yield "mock_db"


@pytest.fixture(autouse=True)
def _override_db():
    app.dependency_overrides[get_db_session] = override_get_db
    yield
    app.dependency_overrides.clear()


@asynccontextmanager
async def _noop_lifespan(app):
    yield


@pytest.fixture
def client():
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.router.lifespan_context = original_lifespan


@pytest.fixture
def mock_topic_manager():
    with patch("app.core.channel_bridge.topic_config.SqlTopicManager") as mock:
        yield mock


def test_get_channel_topics(client, mock_topic_manager):
    # Setup mock
    instance = mock_topic_manager.return_value
    instance.get_all_topics = AsyncMock(
        return_value={
            "chat1": {"__channel__": {"agentId": "agent1", "displayName": "Topic 1"}},
            "__global__": {"__channel__": {"agentId": "global_agent"}},
        }
    )

    # Call API
    response = client.get("/api/v1/channels/manage/whatsapp/topics", headers={"Authorization": "Bearer test"})

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["channel"] == "whatsapp"
    assert data["globalAgentId"] == "global_agent"
    assert len(data["topics"]) == 1
    assert data["topics"][0]["topicId"] == "chat1"
    assert data["topics"][0]["agentId"] == "agent1"
    assert data["topics"][0]["displayName"] == "Topic 1"


def test_bind_topic(client, mock_topic_manager):
    # Setup mock
    instance = mock_topic_manager.return_value

    instance.bind_topic = AsyncMock(return_value=TopicContext(topic_id="topic1", agent_id="agent2"))
    with patch("app.services.agent.agent_service.AgentService.get_agent_by_id", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = MagicMock(id="agent2", skill_ids=[])
        # Call API
        response = client.post(
            "/api/v1/channels/manage/whatsapp/topics/topic1/bind",
            json={"agentId": "agent2", "displayName": "New Name"},
            headers={"Authorization": "Bearer test"},
        )

    # Assert
    assert response.status_code == 200
    instance.bind_topic.assert_called_once()
    args, kwargs = instance.bind_topic.call_args
    assert kwargs.get("channel") == "whatsapp"
    assert kwargs.get("chat_id") == "topic1"
    assert kwargs.get("agent_id") == "agent2"
    assert kwargs.get("display_name") == "New Name"


def test_set_default_agent(client, mock_topic_manager):
    # Setup mock
    instance = mock_topic_manager.return_value

    instance.bind_topic = AsyncMock(return_value=TopicContext(topic_id="__global__", agent_id="global_agent2"))
    with patch("app.services.agent.agent_service.AgentService.get_agent_by_id", new_callable=AsyncMock) as mock_agent:
        mock_agent.return_value = MagicMock(id="global_agent2", skill_ids=[])
        # Call API
        response = client.post(
            "/api/v1/channels/manage/whatsapp/default-agent",
            json={"agentId": "global_agent2"},
            headers={"Authorization": "Bearer test"},
        )

    # Assert
    assert response.status_code == 200
    instance.bind_topic.assert_called_once()
    args, kwargs = instance.bind_topic.call_args
    assert kwargs.get("channel") == "whatsapp"
    assert kwargs.get("chat_id") == "__global__"
    assert kwargs.get("agent_id") == "global_agent2"
