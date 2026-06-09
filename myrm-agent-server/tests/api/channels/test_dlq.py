from contextlib import asynccontextmanager
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core.channel_bridge import get_channel_gateway
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="channels_local")
@pytest.fixture
def mock_gateway():
    gateway = AsyncMock()
    gateway.bus = AsyncMock()
    return gateway


@asynccontextmanager
async def _noop_lifespan(app):
    yield


@pytest.fixture
def client(mock_gateway):
    app.dependency_overrides[get_channel_gateway] = lambda: mock_gateway
    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _noop_lifespan
    if True:
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    app.dependency_overrides.clear()
    app.router.lifespan_context = original_lifespan


def test_get_dlq(client, mock_gateway):
    from myrm_agent_harness.infra.delivery.storage import QueuedDelivery

    mock_delivery = QueuedDelivery(
        id="123",
        channel="telegram",
        recipient="456",
        content={"text": "test"},
        enqueued_at=0.0,
        priority=2,
        retry_count=0,
        last_error="timeout",
        failed_at=0.0,
    )
    mock_gateway.bus.get_dlq_messages.return_value = [mock_delivery]

    response = client.get("/api/v1/channels/dlq")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["id"] == "123"


def test_retry_dlq(client, mock_gateway):
    mock_gateway.bus.retry_dlq_message.return_value = True

    response = client.post("/api/v1/channels/dlq/123/retry")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_gateway.bus.retry_dlq_message.assert_called_once_with("123")


def test_delete_dlq(client, mock_gateway):
    mock_gateway.bus.delete_dlq_message.return_value = True

    response = client.delete("/api/v1/channels/dlq/123")
    assert response.status_code == 200
    assert response.json()["status"] == "success"

    mock_gateway.bus.delete_dlq_message.assert_called_once_with("123")
