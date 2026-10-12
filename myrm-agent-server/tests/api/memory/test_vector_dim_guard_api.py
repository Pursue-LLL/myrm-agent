"""API integration tests for Item 151 VectorDimGuardAndRebuildTaskSuite server endpoints.

Covers:
- Vector collection dimension inspection and match/mismatch detection.
- Non-destructive task-based rebuild execution and failed item diagnostics.
- Mutex task lock conflict returning HTTP 409.
- Status snapshot inspection and 404 error handling.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.vector_dim_guard_router import router as vector_dim_guard_router
from app.services.memory.vector_dim_guard_service import (
    VectorDimGuardService,
    get_vector_dim_guard_service,
)


@pytest.fixture
def isolated_service() -> VectorDimGuardService:
    """Provides an isolated VectorDimGuardService instance."""
    return VectorDimGuardService()


@pytest.fixture
def test_app(isolated_service: VectorDimGuardService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(vector_dim_guard_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_vector_dim_guard_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_inspect_collection_dim_api(
    test_app: FastAPI, isolated_service: VectorDimGuardService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Non-existent collection
        resp = await client.post(
            "/api/v1/memory/vector-dim-guard/inspect",
            json={"collection": "non_existent_col", "expected_dim": 1536},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["exists"] is False
        assert data["needs_rebuild"] is True

        # 2. Existing collection with matching dimension
        isolated_service.guard.register_collection("matched_col", dimension=1536)
        resp2 = await client.post(
            "/api/v1/memory/vector-dim-guard/inspect",
            json={"collection": "matched_col", "expected_dim": 1536},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["exists"] is True
        assert data2["dim_match"] is True
        assert data2["needs_rebuild"] is False

        # 3. Existing collection with dimension mismatch
        resp3 = await client.post(
            "/api/v1/memory/vector-dim-guard/inspect",
            json={"collection": "matched_col", "expected_dim": 768},
        )
        assert resp3.status_code == 200
        data3 = resp3.json()
        assert data3["exists"] is True
        assert data3["dim_match"] is False
        assert data3["needs_rebuild"] is True


@pytest.mark.asyncio
async def test_start_rebuild_success_api(
    test_app: FastAPI, isolated_service: VectorDimGuardService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        isolated_service.guard.register_collection(
            "rebuild_col",
            dimension=384,
            documents={"doc_1": {"content": "text 1"}, "doc_2": {"content": "text 2"}},
        )

        payload = {
            "collection": "rebuild_col",
            "expected_dim": 1536,
            "items": [
                {"id": "doc_1", "text": "text 1"},
                {"id": "doc_2", "text": "text 2"},
                {"id": "doc_err_3", "text": "bad text"},
            ],
            "fail_item_ids": ["doc_err_3"],
        }
        resp = await client.post("/api/v1/memory/vector-dim-guard/rebuild/start", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["phase"] == "completed"
        assert data["progress_pct"] == 100
        assert data["processed_count"] == 2
        assert data["total_count"] == 3
        assert len(data["failed_items"]) == 1
        assert data["failed_items"][0]["item_id"] == "doc_err_3"

        # Verify underlying documents preserved (2 docs preserved from seed)
        assert isolated_service.guard.get_document_count("rebuild_col") == 2


@pytest.mark.asyncio
async def test_start_rebuild_conflict_409_api(
    test_app: FastAPI, isolated_service: VectorDimGuardService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Simulate active lock holder
        isolated_service.orchestrator._active_task_id = "rebuild_active_999"

        payload = {
            "collection": "any_col",
            "expected_dim": 1536,
        }
        resp = await client.post("/api/v1/memory/vector-dim-guard/rebuild/start", json=payload)
        assert resp.status_code == 409
        assert "Another rebuild task" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_get_rebuild_task_status_api(
    test_app: FastAPI, isolated_service: VectorDimGuardService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. 404 for unknown task
        resp = await client.get("/api/v1/memory/vector-dim-guard/rebuild/unknown_task/status")
        assert resp.status_code == 404

        # 2. Start a rebuild task and query its status
        start_payload = {
            "collection": "status_col",
            "expected_dim": 1536,
            "items": [{"id": "item_1"}],
        }
        start_resp = await client.post(
            "/api/v1/memory/vector-dim-guard/rebuild/start", json=start_payload
        )
        task_id = start_resp.json()["task_id"]

        status_resp = await client.get(
            f"/api/v1/memory/vector-dim-guard/rebuild/{task_id}/status"
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["task_id"] == task_id
        assert status_data["phase"] == "completed"
