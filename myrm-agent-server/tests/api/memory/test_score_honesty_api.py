"""Integration and unit tests for score honesty API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.score_honesty_router import router as score_honesty_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create lightweight test FastAPI application hosting the score honesty router."""
    api_app = FastAPI()
    api_app.include_router(score_honesty_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_score_honesty_health(test_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/memory/score-honesty/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "score_honesty"


@pytest.mark.asyncio
async def test_score_honesty_evaluate_endpoint(test_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        payload = {
            "candidates": [
                {
                    "id": "c1",
                    "content": "High similarity and high ranking",
                    "raw_similarity": 0.85,
                    "recency_factor": 1.1,
                    "importance_boost": 1.0,
                    "mmr_penalty": 0.05,
                    "rrf_score": 0.02,
                },
                {
                    "id": "c2",
                    "content": "Low similarity but inflated recency",
                    "raw_similarity": 0.25,
                    "recency_factor": 1.8,
                    "importance_boost": 1.2,
                    "mmr_penalty": 0.0,
                    "rrf_score": 0.03,
                },
            ],
            "config": {
                "raw_similarity_threshold": 0.5,
                "ranking_score_threshold": 0.5,
                "strict_mode": True,
            },
        }

        response = await client.post("/api/memory/score-honesty/evaluate", json=payload)
        assert response.status_code == 200
        body = response.json()

        assert "evaluated" in body
        assert "stats" in body
        assert len(body["evaluated"]) == 2

        # c1 should be admitted
        c1_res = next(c for c in body["evaluated"] if c["id"] == "c1")
        assert c1_res["verdict"]["admitted"] is True
        assert c1_res["verdict"]["passed_raw"] is True
        assert c1_res["breakdown"]["raw_similarity"] == 0.85

        # c2 should be rejected in strict mode due to low raw similarity
        c2_res = next(c for c in body["evaluated"] if c["id"] == "c2")
        assert c2_res["verdict"]["admitted"] is False
        assert c2_res["verdict"]["passed_raw"] is False
        assert c2_res["verdict"]["rejection_stage"] == "raw_below_threshold"

        stats = body["stats"]
        assert stats["total_candidates"] == 2
        assert stats["admitted_count"] == 1
        assert stats["rejected_count"] == 1


@pytest.mark.asyncio
async def test_score_honesty_filter_and_stats(test_app: FastAPI) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        payload = {
            "candidates": [
                {
                    "id": "pass-item",
                    "content": "Passed both thresholds",
                    "raw_similarity": 0.9,
                    "recency_factor": 1.0,
                    "importance_boost": 1.0,
                },
                {
                    "id": "fail-item",
                    "content": "Failed raw threshold",
                    "raw_similarity": 0.1,
                    "recency_factor": 0.5,
                    "importance_boost": 0.5,
                },
            ],
            "config": {
                "raw_similarity_threshold": 0.6,
                "ranking_score_threshold": 0.5,
                "strict_mode": True,
            },
        }

        filter_resp = await client.post("/api/memory/score-honesty/filter", json=payload)
        assert filter_resp.status_code == 200
        filter_data = filter_resp.json()
        assert filter_data["total_admitted"] == 1
        assert filter_data["admitted"][0]["id"] == "pass-item"

        # Check stats endpoint
        stats_resp = await client.get("/api/memory/score-honesty/stats")
        assert stats_resp.status_code == 200
        stats_data = stats_resp.json()
        assert stats_data["total_candidates"] == 2
        assert stats_data["admitted_count"] == 1
