"""Integration tests for Multimodal Vision and Artifact Memory API endpoints.

[POS]
Server-side integration test suite verifying multimodal asset ingestion,
cross-modal search, item detail retrieval, and UI card projection.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.multimodal_memory_router import (
    router as multimodal_memory_router,
)
from app.services.memory.multimodal_memory_service import (
    multimodal_memory_service,
)


@pytest.fixture
def test_app() -> FastAPI:
    """Create isolated FastAPI app mounting multimodal memory router."""
    api_app = FastAPI()
    api_app.include_router(multimodal_memory_router, prefix="/api/memory")
    return api_app


@pytest.fixture(autouse=True)
def reset_service() -> None:
    """Reset multimodal memory store before each test."""
    multimodal_memory_service.clear()


@pytest.mark.asyncio
async def test_multimodal_health_endpoint(test_app: FastAPI) -> None:
    """Verify health endpoint of multimodal memory subsystem."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/memory/multimodal/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["subsystem"] == "multimodal_vision_and_artifact_memory"


@pytest.mark.asyncio
async def test_ingest_and_search_multimodal_asset_api(test_app: FastAPI) -> None:
    """Verify ingestion of vision asset and natural language cross-modal search."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest vision item
        ingest_payload = {
            "title": "用户微服务架构图",
            "description": "用户服务与认证服务的调用关系图",
            "visual_summary": "包含 Gateway, User Service, Redis 缓存节点",
            "file_path": "/sandbox/workspace/user_arch.png",
            "tags": ["architecture", "backend"],
            "session_id": "sess_1001",
        }
        ingest_resp = await client.post(
            "/api/memory/multimodal/ingest",
            json=ingest_payload,
        )
        assert ingest_resp.status_code == 201
        item_data = ingest_resp.json()
        item_id = item_data["item_id"]
        assert item_data["title"] == "用户微服务架构图"
        assert item_data["modality"] == "image"
        assert item_data["artifact_kind"] == "diagram"

        # 2. Search cross-modal by natural language
        search_payload = {
            "query_text": "微服务架构图",
            "limit": 5,
        }
        search_resp = await client.post(
            "/api/memory/multimodal/search",
            json=search_payload,
        )
        assert search_resp.status_code == 200
        search_data = search_resp.json()
        assert search_data["total_matched"] >= 1
        top_hit = search_data["hits"][0]
        assert top_hit["item"]["item_id"] == item_id
        assert top_hit["relevance_score"] >= 0.8
        assert top_hit["card_preview"]["path_status"] == "available"


@pytest.mark.asyncio
async def test_get_multimodal_item_and_card_api(test_app: FastAPI) -> None:
    """Verify item retrieval and UI card projection endpoints."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest an HTML report artifact
        ingest_resp = await client.post(
            "/api/memory/multimodal/ingest",
            json={
                "title": "性能压测汇总表",
                "description": "Locust 性能压测报告导出 HTML",
                "file_path": "/sandbox/volume/perf_report.html",
            },
        )
        assert ingest_resp.status_code == 201
        item_id = ingest_resp.json()["item_id"]

        # 2. Retrieve item detail
        item_resp = await client.get(f"/api/memory/multimodal/items/{item_id}")
        assert item_resp.status_code == 200
        assert item_resp.json()["artifact_kind"] == "report_html"

        # 3. Retrieve card preview
        card_resp = await client.get(f"/api/memory/multimodal/items/{item_id}/card")
        assert card_resp.status_code == 200
        card_data = card_resp.json()
        assert card_data["item_id"] == item_id
        assert card_data["title"] == "性能压测汇总表"
        assert card_data["artifact_kind"] == "report_html"

        # 4. 404 for non-existent item
        not_found_resp = await client.get("/api/memory/multimodal/items/unknown_id")
        assert not_found_resp.status_code == 404
