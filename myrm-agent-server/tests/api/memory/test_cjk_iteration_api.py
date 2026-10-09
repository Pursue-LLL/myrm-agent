"""Integration and unit tests for CJK iteration mark disambiguation and recall API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.cjk_iteration_router import router as cjk_iteration_router


@pytest.fixture
def test_app() -> FastAPI:
    """Create lightweight test FastAPI application hosting the CJK iteration router."""
    api_app = FastAPI()
    api_app.include_router(cjk_iteration_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_cjk_iteration_health(test_app: FastAPI) -> None:
    """Test health check probe endpoint for CJK iteration mark subsystem."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/memory/cjk-iteration/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["module"] == "cjk_iteration_mark"
        assert data["version"] == "1.0.0"


@pytest.mark.asyncio
async def test_disambiguate_endpoint_single_expansion(test_app: FastAPI) -> None:
    """Test expanding a single ideographic iteration mark ('日々' -> '日日')."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/cjk-iteration/disambiguate",
            json={"text": "日々の業務改善"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["original_text"] == "日々の業務改善"
        assert data["normalized_text"] == "日日の業務改善"
        assert data["has_iteration_mark"] is True
        assert data["marks_expanded_count"] == 1

        tokens = data["tokens"]
        assert "日々" in tokens["raw_tokens"]
        assert "日日" in tokens["normalized_tokens"]
        assert "日々" in tokens["all_tokens"]
        assert "日日" in tokens["all_tokens"]


@pytest.mark.asyncio
async def test_disambiguate_endpoint_chained_expansion(test_app: FastAPI) -> None:
    """Test multi-token consecutive iteration mark resolution ('代々々々' -> '代代代代')."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/cjk-iteration/disambiguate",
            json={"text": "代々々々伝承"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["normalized_text"] == "代代代代伝承"
        assert data["marks_expanded_count"] == 3
        tokens = data["tokens"]
        assert "代代" in tokens["normalized_tokens"]


@pytest.mark.asyncio
async def test_disambiguate_endpoint_invalid_antecedent_blocked(
    test_app: FastAPI,
) -> None:
    """Test invalid antecedents (hiragana, punctuation) do not expand."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/cjk-iteration/disambiguate",
            json={"text": "あ々 テスト 々"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["marks_expanded_count"] == 0
        assert data["normalized_text"] == "あ々 テスト 々"


@pytest.mark.asyncio
async def test_match_endpoint_bidirectional_recall(test_app: FastAPI) -> None:
    """Test matching when query has iteration mark and memory target has normalized text."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Query with iteration mark vs memory item with resolved kanji
        response = await client.post(
            "/api/memory/cjk-iteration/match",
            json={
                "query": "日々の反省",
                "target_text": "日日の反省と計画策定",
                "threshold": 0.1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_matched"] is True
        assert data["composite_score"] > 0.0
        assert data["normalized_overlap_count"] >= 1
        assert "日日" in data["matched_tokens"]

        # Inverse: Query with resolved kanji vs memory item with iteration mark
        inv_response = await client.post(
            "/api/memory/cjk-iteration/match",
            json={
                "query": "日日の反省",
                "target_text": "日々の反省と計画策定",
                "threshold": 0.1,
            },
        )
        assert inv_response.status_code == 200
        inv_data = inv_response.json()
        assert inv_data["is_matched"] is True
        assert inv_data["composite_score"] > 0.0


@pytest.mark.asyncio
async def test_match_endpoint_unrelated_target(test_app: FastAPI) -> None:
    """Test negative recall matching for semantically/lexically disjoint text."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/memory/cjk-iteration/match",
            json={
                "query": "日々の勉強",
                "target_text": "東京タワーの観光案内",
                "threshold": 0.1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["is_matched"] is False
        assert data["composite_score"] == 0.0
        assert len(data["matched_tokens"]) == 0
