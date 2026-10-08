"""Integration tests for Experience Compounding and Knowledge Condensation API.

[POS]
Integration tests verifying experience registration, logarithmic reinforcement,
semantic Golden Rule synthesis, rollback decondensation, annealing, and stats.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.experience_compounding_router (router)
- app.services.memory.experience_compounding.provider (
  ExperienceCompoundingServiceProvider, get_experience_compounding_service)

[OUTPUT]
- Test functions covering experience compounding API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.experience_compounding_router import (
    router as experience_compounding_router,
)
from app.services.memory.experience_compounding.provider import (
    ExperienceCompoundingServiceProvider,
    get_experience_compounding_service,
)


@pytest.fixture
def isolated_service() -> ExperienceCompoundingServiceProvider:
    """Create isolated provider instance for testing."""
    return ExperienceCompoundingServiceProvider()


@pytest.fixture
def test_app(isolated_service: ExperienceCompoundingServiceProvider) -> FastAPI:
    """Create FastAPI test application with isolated dependency override."""
    api_app = FastAPI()
    api_app.include_router(experience_compounding_router, prefix="/api/memory")
    api_app.dependency_overrides[get_experience_compounding_service] = (
        lambda: isolated_service
    )
    return api_app


@pytest.mark.asyncio
async def test_add_and_reinforce_experience(test_app: FastAPI) -> None:
    """Verify adding an experience item and reinforcing its compounding weight."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # 1. Add experience item
        add_resp = await client.post(
            "/api/memory/compounding/item",
            json={
                "content": "偏好使用 UV 包管理器替代传统 pip 工具",
                "topic": "toolchain",
                "base_weight": 1.0,
                "tags": ["python", "packaging"],
            },
        )
        assert add_resp.status_code == 201
        data = add_resp.json()
        item_id = data["item_id"]
        assert data["compounded_weight"] == 1.0
        assert data["topic"] == "toolchain"

        # 2. Reinforce adoption
        reinf_resp = await client.post(
            "/api/memory/compounding/reinforce",
            json={"item_id": item_id, "adopted": True},
        )
        assert reinf_resp.status_code == 200
        reinf_data = reinf_resp.json()
        assert reinf_data["status"] == "reinforced"
        assert reinf_data["new_weight"] > 1.0


@pytest.mark.asyncio
async def test_condense_and_decondense_lifecycle(test_app: FastAPI) -> None:
    """Verify semantic Golden Rule condensation and non-destructive decondensation rollback."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # The seeded service contains 2 frontend items (TailwindCSS and Flexbox)
        cond_resp = await client.post("/api/memory/compounding/condense")
        assert cond_resp.status_code == 200
        cond_data = cond_resp.json()
        assert cond_data["rules_generated"]
        assert cond_data["clusters_found"] >= 1
        assert cond_data["fragments_archived"] >= 2

        rule = cond_data["rules_generated"][0]
        rule_id = rule["rule_id"]
        assert rule["topic"] == "frontend"
        assert len(rule["source_fragment_ids"]) >= 2

        # Verify Golden Rules endpoint
        rules_resp = await client.get("/api/memory/compounding/rules")
        assert rules_resp.status_code == 200
        assert any(r["rule_id"] == rule_id for r in rules_resp.json())

        # Roll back decondensation
        decond_resp = await client.post(
            "/api/memory/compounding/decondense",
            json={"rule_id": rule_id},
        )
        assert decond_resp.status_code == 200
        reactivated = decond_resp.json()
        assert len(reactivated) >= 2
        assert all(it["state"] == "active" for it in reactivated)


@pytest.mark.asyncio
async def test_anneal_endpoint(test_app: FastAPI) -> None:
    """Verify obsolete context annealing endpoint execution."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        resp = await client.post("/api/memory/compounding/anneal")
        assert resp.status_code == 200
        data = resp.json()
        assert data["inspected_count"] >= 1
        # Pinned item in seed should be exempted
        assert data["active_lease_exempt_count"] >= 1


@pytest.mark.asyncio
async def test_stats_and_active_endpoints(test_app: FastAPI) -> None:
    """Verify operational statistics and active fragments list endpoints."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        stats_resp = await client.get("/api/memory/compounding/stats")
        assert stats_resp.status_code == 200
        stats = stats_resp.json()
        assert stats["total_items"] >= 4
        assert stats["active_items"] >= 3

        active_resp = await client.get("/api/memory/compounding/active")
        assert active_resp.status_code == 200
        active_items = active_resp.json()
        assert len(active_items) == stats["active_items"]
