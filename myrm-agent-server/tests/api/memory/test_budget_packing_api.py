# [POS]: tests/api/memory/test_budget_packing_api.py
# [INPUT]: app.api.memory.budget_packing_router, app.services.memory.budget_packing_service, FastAPI app
# [OUTPUT]: Integration API tests for Budget Greedy Marginal Value Recall Packing Suite (Item 122)

"""Integration API tests for Budget Greedy Marginal Value Recall Packing Suite (Item 122)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.budget_packing_router import (
    router as budget_packing_router,
)
from app.services.memory.budget_packing_service import (
    BudgetPackingService,
    get_budget_packing_service,
)


@pytest.fixture
def isolated_service() -> BudgetPackingService:
    """Provides an isolated BudgetPackingService instance."""
    return BudgetPackingService()


@pytest.fixture
def test_app(isolated_service: BudgetPackingService) -> FastAPI:
    """Creates a test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(budget_packing_router, prefix="/api/memory")
    app.dependency_overrides[get_budget_packing_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_get_default_budget_api(test_app: FastAPI) -> None:
    """Validate getting default token budget and diversity parameters."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/memory/budget-packing/default-budget")
        assert res.status_code == 200
        data = res.json()
        assert data["max_billed_tokens"] == 1000
        assert data["diversity_penalty_lambda"] == 0.65
        assert data["min_marginal_value_threshold"] == 0.05
        assert data["max_redundancy_threshold"] == 0.45
        assert data["allow_greedy_backfill"] is True


@pytest.mark.asyncio
async def test_pack_recall_candidates_greedy_api(test_app: FastAPI) -> None:
    """Validate greedy knapsack packing, redundancy pruning, and dual-track accounting."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        candidates = [
            {
                "id": "c1",
                "content": "核心架构准则：所有新建文件单文件行数不超过400行。",
                "relevance_score": 0.95,
                "confidence_score": 1.0,
                "billed_tokens": 40,
                "storage_tokens": 100,
                "domain_tags": ["architecture"],
            },
            {
                "id": "c2",
                "content": "核心架构准则：所有新建文件单文件行数不能超过400行严格规范。",
                "relevance_score": 0.90,
                "confidence_score": 1.0,
                "billed_tokens": 40,
                "storage_tokens": 90,
                "domain_tags": ["architecture"],
            },
            {
                "id": "c3",
                "content": "质量红线：严格禁止使用 any 类型，必须使用具体 Type Hints。",
                "relevance_score": 0.85,
                "confidence_score": 1.0,
                "billed_tokens": 30,
                "storage_tokens": 80,
                "domain_tags": ["typing"],
            },
        ]

        payload = {
            "candidates": candidates,
            "budget": {
                "max_billed_tokens": 80,
                "diversity_penalty_lambda": 0.8,
                "max_redundancy_threshold": 0.45,
                "allow_greedy_backfill": True,
            },
            "enable_knapsack": True,
        }

        res = await client.post("/api/memory/budget-packing/pack", json=payload)
        assert res.status_code == 200
        data = res.json()

        packed = data["packed_items"]
        dropped = data["dropped_candidates"]
        accounting = data["accounting"]

        # c1 and c3 packed, c2 suppressed by redundancy
        packed_ids = [p["candidate"]["id"] for p in packed]
        assert "c1" in packed_ids
        assert "c3" in packed_ids
        assert "c2" not in packed_ids

        assert len(dropped) == 1
        assert dropped[0]["reason"] == "redundancy_suppressed"

        # Verify dual-track token accounting
        assert accounting["total_candidates_examined"] == 3
        assert accounting["items_packed_count"] == 2
        assert accounting["billed_tokens_spent"] == 70
        assert accounting["storage_tokens_total"] == 270
        assert accounting["storage_tokens_saved"] == 90
        assert accounting["redundant_tokens_filtered"] == 40
        assert accounting["budget_utilization_pct"] == 87.5

        # Check prompt block presence
        assert "<recalled_memories" in data["composed_prompt_block"]
        assert "</recalled_memories>" in data["composed_prompt_block"]


@pytest.mark.asyncio
async def test_inspect_marginal_values_api(test_app: FastAPI) -> None:
    """Validate sequential inspection of marginal value metrics."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        candidates = [
            {
                "id": "c1",
                "content": "前端状态管理采用 Zustand 轻量状态机。",
                "relevance_score": 0.90,
                "billed_tokens": 25,
            },
            {
                "id": "c2",
                "content": "后端任务调度采用 Redis 和 Celery 分布式队列。",
                "relevance_score": 0.80,
                "billed_tokens": 30,
            },
        ]

        res = await client.post(
            "/api/memory/budget-packing/inspect-marginal",
            json={"candidates": candidates},
        )
        assert res.status_code == 200
        items = res.json()
        assert len(items) == 2
        assert items[0]["candidate"]["id"] == "c1"
        assert items[0]["metrics"]["redundancy_score"] == 0.0
        assert items[1]["candidate"]["id"] == "c2"
        assert items[1]["metrics"]["marginal_value_density"] > 0
