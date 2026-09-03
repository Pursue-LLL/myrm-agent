"""Integration tests for Channel Data Plane HTTP management endpoints.

Covers:
- GET /api/v1/channels/manage/{channel}/data-plane
- POST /api/v1/channels/manage/{channel}/data-plane/prune
- POST /api/v1/channels/manage/{channel}/data-plane/clear
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.channels.data_plane import router as data_plane_router
from app.database.connection import get_db


@pytest.fixture
def test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(data_plane_router, prefix="/api/v1/channels/manage")
    return app


@pytest.fixture
def client(test_app: FastAPI) -> TestClient:
    return TestClient(test_app)


def test_get_data_plane_stats(client: TestClient, test_app: FastAPI) -> None:
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    test_app.dependency_overrides[get_db] = override_get_db

    with patch(
        "app.api.channels.data_plane.ChannelMessageRepository.get_channel_stats",
        new_callable=AsyncMock,
    ) as mock_stats:
        mock_stats.return_value = {
            "total_messages": 10,
            "learning_eligible": 8,
            "trigger_messages": 3,
        }

        resp = client.get("/api/v1/channels/manage/feishu/data-plane")
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == "feishu"
        assert data["total_messages"] == 10
        assert data["learning_eligible"] == 8
        assert data["trigger_messages"] == 3
        assert data["ambient_messages"] == 7
        assert data["secret_scrubber_active"] is True


def test_prune_data_plane(client: TestClient, test_app: FastAPI) -> None:
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    test_app.dependency_overrides[get_db] = override_get_db

    with patch(
        "app.api.channels.data_plane.ChannelMessageRepository.prune_expired",
        new_callable=AsyncMock,
    ) as mock_prune:
        mock_prune.return_value = 5

        resp = client.post(
            "/api/v1/channels/manage/feishu/data-plane/prune",
            json={"retention_days": 30},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == "feishu"
        assert data["pruned_count"] == 5
        assert data["success"] is True


def test_clear_data_plane(client: TestClient, test_app: FastAPI) -> None:
    mock_db = AsyncMock()

    async def override_get_db():
        yield mock_db

    test_app.dependency_overrides[get_db] = override_get_db

    with patch(
        "app.api.channels.data_plane.ChannelMessageRepository.clear_chat_history",
        new_callable=AsyncMock,
    ) as mock_clear:
        mock_clear.return_value = 12

        resp = client.post(
            "/api/v1/channels/manage/feishu/data-plane/clear",
            json={"chat_id": "chat_001"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["channel"] == "feishu"
        assert data["deleted_count"] == 12
        assert data["success"] is True
