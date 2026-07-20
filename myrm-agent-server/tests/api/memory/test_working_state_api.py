"""Unit tests for /memory/working-state API endpoints."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.memory._internal.storage import (
    WORKING_STATE_PROFILE_KEY,
    WORKING_STATE_TTL_DAYS,
    WORKING_STATE_UPDATED_AT_KEY,
)

from app.api.dependencies import get_deploy_identity
from app.api.memory.utils import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="memory")


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[get_deploy_identity] = lambda: {"id": "test_user", "username": "test"}
    with patch("app.core.security.auth.identity.is_loopback_ip", return_value=True):
        yield
    app.dependency_overrides.pop(get_deploy_identity, None)


@pytest.fixture
def mock_memory_manager():
    mock = AsyncMock()
    store: dict[str, str] = {}

    async def get_attr(key: str):
        return store.get(key)

    async def set_attr(key: str, value: str):
        store[key] = value

    async def delete_attr(key: str):
        store.pop(key, None)
        return True

    mock.get_profile_attribute.side_effect = get_attr
    mock.set_system_profile_attribute.side_effect = set_attr
    mock.delete_system_profile_attribute.side_effect = delete_attr
    mock._store = store
    return mock


@pytest.fixture(autouse=True)
def override_memory(mock_memory_manager):
    app.dependency_overrides[get_crud_memory_manager] = lambda: mock_memory_manager
    yield
    app.dependency_overrides.pop(get_crud_memory_manager, None)


class TestGetWorkingState:
    def test_empty_state(self, client: TestClient):
        resp = client.get("/api/v1/memory/working-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] is None
        assert data["expired"] is False

    def test_active_state(self, client: TestClient, mock_memory_manager):
        now = datetime.now(UTC).isoformat()
        mock_memory_manager._store[WORKING_STATE_PROFILE_KEY] = "Task: refactor API"
        mock_memory_manager._store[WORKING_STATE_UPDATED_AT_KEY] = now

        resp = client.get("/api/v1/memory/working-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Task: refactor API"
        assert data["expired"] is False
        assert data["ttl_days"] == WORKING_STATE_TTL_DAYS

    def test_expired_state(self, client: TestClient, mock_memory_manager):
        old_time = (datetime.now(UTC) - timedelta(days=WORKING_STATE_TTL_DAYS + 1)).isoformat()
        mock_memory_manager._store[WORKING_STATE_PROFILE_KEY] = "Old task"
        mock_memory_manager._store[WORKING_STATE_UPDATED_AT_KEY] = old_time

        resp = client.get("/api/v1/memory/working-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "Old task"
        assert data["expired"] is True


class TestUpdateWorkingState:
    def test_update_success(self, client: TestClient, mock_memory_manager):
        resp = client.put("/api/v1/memory/working-state", json={"content": "New task progress"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] == "New task progress"
        assert data["updated_at"] is not None
        assert mock_memory_manager._store[WORKING_STATE_PROFILE_KEY] == "New task progress"

    def test_update_max_length(self, client: TestClient):
        long_content = "x" * 501
        resp = client.put("/api/v1/memory/working-state", json={"content": long_content})
        assert resp.status_code == 422

    def test_update_exactly_max_length(self, client: TestClient):
        content = "x" * 500
        resp = client.put("/api/v1/memory/working-state", json={"content": content})
        assert resp.status_code == 200
        assert resp.json()["content"] == content

    def test_update_empty_content(self, client: TestClient):
        resp = client.put("/api/v1/memory/working-state", json={"content": ""})
        assert resp.status_code == 200


class TestClearWorkingState:
    def test_clear_success(self, client: TestClient, mock_memory_manager):
        mock_memory_manager._store[WORKING_STATE_PROFILE_KEY] = "Some task"
        mock_memory_manager._store[WORKING_STATE_UPDATED_AT_KEY] = datetime.now(UTC).isoformat()

        resp = client.delete("/api/v1/memory/working-state")
        assert resp.status_code == 200
        data = resp.json()
        assert data["content"] is None
        assert WORKING_STATE_PROFILE_KEY not in mock_memory_manager._store
        assert WORKING_STATE_UPDATED_AT_KEY not in mock_memory_manager._store

    def test_clear_already_empty(self, client: TestClient):
        resp = client.delete("/api/v1/memory/working-state")
        assert resp.status_code == 200
        assert resp.json()["content"] is None
