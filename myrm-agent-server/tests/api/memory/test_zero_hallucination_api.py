# [POS] tests/api/memory/test_zero_hallucination_api.py
# [INPUT] FastAPI, httpx.AsyncClient, app.api.memory.zero_hallucination
# [OUTPUT] TestZeroHallucinationAPISuite

"""Integration tests for zero-hallucination memory diagnostics and guarded search API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.zero_hallucination import router as zero_hallucination_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting zero-hallucination diagnostics router."""
    api_app = FastAPI()
    api_app.include_router(zero_hallucination_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_query_with_facts_success(test_app: FastAPI) -> None:
    """Verify standard query returns matched facts with strict adherence instructions."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/diagnostics/query",
            json={"query": "python style preferences"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "found"
        assert data["total_matched"] == 2
        assert len(data["facts"]) == 2
        assert data["is_degraded"] is False
        assert "Retrieved Historical Facts" in data["wrapped_context"]
        assert "<!-- ZERO_HALLUCINATION_MEMORY_BEGIN -->" in data["wrapped_context"]


@pytest.mark.asyncio
async def test_query_explicit_empty_rejection(test_app: FastAPI) -> None:
    """Verify empty query yields EXPLICIT_EMPTY state with anti-fabrication mandate."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/diagnostics/query",
            json={"query": "unknown dark matter physics empty"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "explicit_empty"
        assert data["total_matched"] == 0
        assert data["facts"] == []
        assert "EXPLICIT_EMPTY" in data["guard_instruction"]
        assert "DO NOT guess" in data["guard_instruction"]
        assert "<!-- ZERO_HALLUCINATION_MEMORY_BEGIN -->" in data["wrapped_context"]


@pytest.mark.asyncio
async def test_query_service_offline_rejection(test_app: FastAPI) -> None:
    """Verify offline simulation returns explicit SERVICE_UNAVAILABLE state with 0 facts."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/diagnostics/query",
            json={"query": "my favorite database", "simulate_offline": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "service_unavailable"
        assert data["total_matched"] == 0
        assert data["is_degraded"] is True
        assert data["error_code"] == "SERVICE_OFFLINE_503"
        assert "SERVICE_UNAVAILABLE" in data["wrapped_context"]


@pytest.mark.asyncio
async def test_query_partial_degradation_handling(test_app: FastAPI) -> None:
    """Verify partial degradation preserves surviving facts and flags degraded subsystems."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/diagnostics/query",
            json={
                "query": "coding preferences",
                "simulated_degraded_sources": ["qdrant_subsystem_shard_3"],
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["state"] == "partial_degraded"
        assert data["total_matched"] == 1
        assert data["is_degraded"] is True
        assert data["degraded_sources"] == ["qdrant_subsystem_shard_3"]
        assert "PARTIAL_DEGRADED" in data["guard_instruction"]
        assert "Surviving verified profile preference" in data["wrapped_context"]


@pytest.mark.asyncio
async def test_diagnostics_health_api(test_app: FastAPI) -> None:
    """Verify memory subsystems health diagnostics endpoint."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/memory/diagnostics/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "HEALTHY"
        assert data["total_subsystems"] >= 3
        assert data["online_count"] == data["total_subsystems"]
        assert len(data["subsystems"]) >= 3
