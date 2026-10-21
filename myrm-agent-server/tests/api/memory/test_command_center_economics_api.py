"""Contract tests for Memory Economics endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_db_session
from app.api.memory.operations import command_center as command_center_operation
from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.command_center import (
    MemoryCommandCostProfile,
    MemoryCommandEconomicsDashboard,
    MemoryCommandParasiticMemory,
    MemoryCommandTurnEconomics,
)


@pytest.fixture
def economics_client() -> TestClient:
    app = FastAPI()
    app.include_router(command_center_operation.router, prefix="/api/memory")

    async def _mock_db() -> AsyncMock:

        return AsyncMock()

    def _mock_manager() -> MagicMock:
        return MagicMock()

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_crud_memory_manager] = _mock_manager
    return TestClient(app)


def test_get_economics_endpoint(economics_client: TestClient) -> None:
    mock_dashboard = MemoryCommandEconomicsDashboard(
        cost_profile=MemoryCommandCostProfile(
            prompt_tokens=5000,
            cached_tokens=4000,
            completion_tokens=600,
            cited_memory_refs=8,
            estimated_memory_tokens=800,
            cache_friendly=True,
            construction_ms=120.5,
            retrieval_ms=32.1,
            injection_overhead_ms=1.5,
            effective_cited_tokens=520,
            background_construction_tokens=60,
            cache_preservation_score=0.80,
            roi_percentage=65.0,
            roi_grade="optimal",
            parasitic_memory_count=1,
        ),
        turn_trajectories=[
            MemoryCommandTurnEconomics(
                turn_index=1,
                message_id="msg-1",
                injected_tokens=400,
                cited_tokens=260,
                cached_tokens=2000,
                roi_percentage=65.0,
                cache_aligned=True,
                retrieval_ms=32.1,
            )
        ],
        parasitic_memories=[
            MemoryCommandParasiticMemory(
                memory_id="mem-stale-99",
                memory_type="semantic",
                content_preview="Outdated design guidelines from 2024",
                injected_turns_count=3,
                cited_turns_count=0,
                wasted_tokens_estimated=350,
                suggested_action="archive",
            )
        ],
        estimated_cost_savings_usd=0.0011,
        recommendations=["发现 1 条长期未被引用的沉睡记忆，建议通过 Memory Doctor 进行一键归档。"],
    )

    with (
        patch(
            "app.services.memory.command_center.command_center_insights.MemoryCommandCenterInsights.build_influence",
            new=AsyncMock(return_value=[]),
        ),
        patch(
            "app.api.memory.operations.command_center.MemoryEconomicsService.build_economics_dashboard",
            new=AsyncMock(return_value=mock_dashboard),
        ),
    ):
        resp = economics_client.get("/api/memory/command-center/economics?limit_turns=20")
        assert resp.status_code == 200

        data = resp.json()
        assert data["cost_profile"]["roi_grade"] == "optimal"
        assert data["cost_profile"]["construction_ms"] == 120.5
        assert data["cost_profile"]["retrieval_ms"] == 32.1
        assert len(data["turn_trajectories"]) == 1
        assert len(data["parasitic_memories"]) == 1
        assert data["parasitic_memories"][0]["memory_id"] == "mem-stale-99"
        assert data["parasitic_memories"][0]["suggested_action"] == "archive"
        assert data["estimated_cost_savings_usd"] == 0.0011
