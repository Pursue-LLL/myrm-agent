"""Unit and integration tests for /statistics/learning-loop/status endpoint."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.statistics.learning_loop import (
    LearningLoopFiveRingStatusResponse,
    Ring1ReflectionStatus,
    Ring2DistillationStatus,
    Ring3AdvancementStatus,
    Ring4ConsolidationStatus,
    Ring5ProfilingStatus,
)
from app.services.memory.manager_deps import get_crud_memory_manager
from tests.support.minimal_app import build_minimal_app


class TestLearningLoopSchemas:
    """Validate Pydantic models for learning loop status."""

    def test_schema_defaults(self):
        resp = LearningLoopFiveRingStatusResponse(
            ring1_reflection=Ring1ReflectionStatus(),
            ring2_distillation=Ring2DistillationStatus(),
            ring3_advancement=Ring3AdvancementStatus(),
            ring4_consolidation=Ring4ConsolidationStatus(),
            ring5_profiling=Ring5ProfilingStatus(),
        )
        assert resp.overall_loop_health_score == 100
        assert resp.overall_status == "optimal"
        assert resp.ring1_reflection.is_active is True
        assert resp.ring2_distillation.total_active_skills == 0
        assert resp.ring3_advancement.regressions_blocked == 0
        assert resp.ring4_consolidation.memory_health_score == 100
        assert resp.ring5_profiling.cross_session_recall_ready is True


@pytest.fixture()
def app():
    return build_minimal_app(preset="statistics")


@pytest.fixture()
async def client(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
class TestLearningLoopIntegration:
    """Full HTTP routing integration tests for learning loop status."""

    async def test_get_learning_loop_status_endpoint(self, app, client):
        mock_manager = AsyncMock()
        mock_mem = SimpleNamespace(
            id="mem-1",
            content="test fact",
            created_at=datetime.now(UTC),
            importance=0.8,
            confidence=0.9,
            is_user_locked=False,
            scope=SimpleNamespace(agent_id="default"),
            tags=[],
            status="active",
            source_chat_id="chat-1",
            preference_type=None,
        )
        mock_manager.list.return_value = [mock_mem]
        app.dependency_overrides[get_crud_memory_manager] = lambda: mock_manager

        with (
            patch(
                "app.api.statistics.learning_loop.skills_service.list_skills",
                new_callable=AsyncMock,
                return_value=[{"id": "skill-1", "name": "deploy_app"}],
            ),
            patch(
                "app.api.statistics.learning_loop.list_skill_growth_timeline",
                new_callable=AsyncMock,
                return_value=[
                    SimpleNamespace(
                        status="approved", created_at="2026-08-20T10:00:00Z"
                    ),
                    SimpleNamespace(
                        status="pending", created_at="2026-08-20T11:00:00Z"
                    ),
                ],
            ),
        ):
            resp = await client.get("/api/v1/statistics/learning-loop/status?days=30")
            assert resp.status_code == 200
            data = resp.json()
            assert data["code"] == 0
            payload = data["data"]
            assert "ring1_reflection" in payload
            assert "ring2_distillation" in payload
            assert "ring3_advancement" in payload
            assert "ring4_consolidation" in payload
            assert "ring5_profiling" in payload
            assert payload["overall_loop_health_score"] == 100
            assert payload["overall_status"] == "optimal"
            assert payload["ring2_distillation"]["total_active_skills"] == 1
            assert payload["ring2_distillation"]["proposals_approved"] == 1
