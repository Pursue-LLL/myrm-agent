"""[POS]: tests/api/memory/test_lifecycle_hotness_api.py
[INPUT]: FastAPI TestClient and memory lifecycle hotness endpoints.
[OUTPUT]: Pytest integration tests verifying single entity hotness calculation and blended anti-stale reranking.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.lifecycle_hotness_router import (
    router as hotness_router,
)
from app.services.memory.lifecycle_hotness_service import (
    LifecycleHotnessService,
    get_lifecycle_hotness_service,
)


@pytest.fixture
def app() -> FastAPI:
    """Create isolated FastAPI instance mounting lifecycle hotness router."""
    test_app = FastAPI()
    test_app.include_router(hotness_router)
    test_app.dependency_overrides[get_lifecycle_hotness_service] = (
        lambda: LifecycleHotnessService()
    )
    return test_app


@pytest.fixture
async def client(app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Create async HTTP client for FastAPI test app."""
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac


@pytest.mark.anyio
async def test_score_single_api(client: AsyncClient) -> None:
    """Verify single entity hotness calculation and classification endpoint."""
    now_str = "2026-10-08T12:00:00Z"

    # 1. Fresh zero-access item -> score=0.5, stage=warm
    payload_fresh = {
        "active_count": 0,
        "updated_at": now_str,
        "half_life_days": 7.0,
        "now": now_str,
    }
    resp_fresh = await client.post("/lifecycle-hotness/score", json=payload_fresh)
    assert resp_fresh.status_code == 200
    data_fresh = resp_fresh.json()
    assert data_fresh["hotness_score"] == pytest.approx(0.5, rel=1e-3)
    assert data_fresh["lifecycle_stage"] == "warm"

    # 2. High-frequency item -> score > 0.95, stage=hot
    payload_hot = {
        "active_count": 50,
        "updated_at": now_str,
        "half_life_days": 7.0,
        "now": now_str,
    }
    resp_hot = await client.post("/lifecycle-hotness/score", json=payload_hot)
    assert resp_hot.status_code == 200
    data_hot = resp_hot.json()
    assert data_hot["hotness_score"] > 0.95
    assert data_hot["lifecycle_stage"] == "hot"


@pytest.mark.anyio
async def test_blend_rerank_api(client: AsyncClient) -> None:
    """Verify batch blended reranking endpoint ensures recent active memories surpass stale ones."""
    base_t = datetime(2026, 10, 8, 12, 0, 0, tzinfo=timezone.utc)
    t_stale = (base_t - timedelta(days=28.0)).isoformat()
    t_active = (base_t - timedelta(hours=1.0)).isoformat()
    now_str = base_t.isoformat()

    payload = {
        "items": [
            {
                "id": "mem://rules/old_deprecated_rule",
                "active_count": 1,
                "updated_at": t_stale,
                "semantic_score": 0.94,
            },
            {
                "id": "mem://rules/new_promoted_rule",
                "active_count": 15,
                "updated_at": t_active,
                "semantic_score": 0.88,
            },
        ],
        "blend_alpha": 0.3,
        "half_life_days": 7.0,
        "now": now_str,
    }

    resp = await client.post("/lifecycle-hotness/blend-rerank", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["items"]) == 2

    # Promoted new rule must rank 1st
    first = data["items"][0]
    assert first["id"] == "mem://rules/new_promoted_rule"
    assert first["lifecycle_stage"] == "hot"
    assert first["blended_score"] > data["items"][1]["blended_score"]

    # Old deprecated rule must rank 2nd and classified as cold
    second = data["items"][1]
    assert second["id"] == "mem://rules/old_deprecated_rule"
    assert second["lifecycle_stage"] == "cold"

    # Batch summary metrics
    assert data["hot_count"] == 1
    assert data["cold_count"] == 1
    assert data["warm_count"] == 0
    assert 0.0 < data["avg_hotness"] < 1.0
