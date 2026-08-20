"""Integration tests for /statistics/learning-timeline HTTP endpoints.

Tests the full HTTP request-response cycle using minimal FastAPI app with real routing.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.services.memory.manager_deps import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app


@pytest.fixture()
def app():
    return build_minimal_app(preset="statistics")


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestLearningTimelineIntegration:
    """Full HTTP routing integration tests for learning timeline."""

    async def test_get_learning_timeline_endpoint(self, app, client):
        mock_manager = AsyncMock()
        mock_mem = SimpleNamespace(
            id="mem-int-1",
            content="Integration test memory",
            created_at=datetime.now(UTC),
            importance=0.8,
            confidence=0.9,
            is_user_locked=False,
            scope=SimpleNamespace(agent_id="test-agent"),
            tags=["integration"],
            status="active",
            source_chat_id="chat-1",
            preference_type=None,
        )
        mock_manager.list_memories.return_value = [mock_mem]
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager

        with patch(
            "app.api.statistics.learning_timeline.list_skill_growth_timeline",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = await client.get("/statistics/learning-timeline?days=30&limit=10")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert "items" in data["data"]
            assert data["data"]["total_count"] >= 1

    async def test_put_learning_timeline_memory_endpoint(self, app, client):
        mock_manager = AsyncMock()
        mock_mem = SimpleNamespace(
            id="mem-1",
            content="Updated content via HTTP",
            importance=0.9,
            reasoning="Context",
            tags=["python"],
            is_user_locked=True,
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        mock_manager.update_memory.return_value = mock_mem
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager

        with patch(
            "app.api.statistics.learning_timeline._record_memory_event",
            new_callable=AsyncMock,
        ):
            resp = await client.put(
                "/statistics/learning-timeline/memory/semantic/mem-1",
                json={
                    "content": "Updated content via HTTP",
                    "importance": 0.9,
                    "reasoning": "Context",
                },
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert data["data"]["content"] == "Updated content via HTTP"

    async def test_delete_learning_timeline_memory_endpoint(self, app, client):
        mock_manager = AsyncMock()
        mock_manager.delete_memory.return_value = True
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager

        with patch(
            "app.api.statistics.learning_timeline._record_memory_event",
            new_callable=AsyncMock,
        ):
            resp = await client.delete("/statistics/learning-timeline/memory/mem-1?memory_type=semantic")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            assert data["data"]["deleted"] is True
