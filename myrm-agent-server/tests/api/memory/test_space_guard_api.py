"""Integration tests for embedding model dimension and vector space guard API.

[POS]
Integration test verifying space compatibility validation, model base drift defense,
fingerprint binding, diagnostic status probes, and reindexing pipeline endpoints.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.space_guard (router, get_space_guard_service)
- app.services.memory.space_guard (VectorSpaceGuardService)
- app.schemas.space_guard (
    SpaceBindRequest,
    SpaceFingerprintDTO,
    SpaceReindexRequest,
    SpaceValidateRequest,
  )

[OUTPUT]
- Test functions covering vector space guard API.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.space_guard import get_space_guard_service
from app.api.memory.space_guard import router as space_guard_router
from app.services.memory.space_guard.provider import VectorSpaceGuardService


@pytest.fixture
def isolated_service() -> VectorSpaceGuardService:
    """Create isolated service instance."""
    return VectorSpaceGuardService()


@pytest.fixture
def test_app(isolated_service: VectorSpaceGuardService) -> FastAPI:
    """Create FastAPI test application with injected isolated service."""
    api_app = FastAPI()
    api_app.include_router(space_guard_router, prefix="/api/memory")
    api_app.dependency_overrides[get_space_guard_service] = lambda: isolated_service
    return api_app


@pytest.mark.asyncio
async def test_validate_uninitialized_and_auto_bind(test_app: FastAPI) -> None:
    """Verify validation behavior on uninitialized space with and without auto-bind."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        fp_payload = {
            "provider_id": "openai",
            "model_name": "text-embedding-3-small",
            "vector_dimension": 1536,
            "metric_type": "cosine",
            "config_hash": "hash_sample",
        }

        # 1. Without auto_bind -> should be uninitialized
        resp1 = await client.post(
            "/api/memory/space-guard/validate",
            json={
                "collection": "coll_uninit",
                "fingerprint": fp_payload,
                "auto_bind_if_empty": False,
            },
        )
        assert resp1.status_code == 200
        data1 = resp1.json()
        assert data1["is_valid"] is False
        assert data1["status"] == "uninitialized"
        assert data1["recommended_action"] == "initialize_space"

        # 2. With auto_bind -> should automatically bind and succeed
        resp2 = await client.post(
            "/api/memory/space-guard/validate",
            json={
                "collection": "coll_uninit",
                "fingerprint": fp_payload,
                "auto_bind_if_empty": True,
            },
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["is_valid"] is True
        assert data2["status"] == "consistent"
        assert data2["recommended_action"] == "proceed"


@pytest.mark.asyncio
async def test_validate_dimension_and_model_base_mismatch(test_app: FastAPI) -> None:
    """Verify dimension divergence and model base drift are strictly identified."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        coll = "guarded_coll"
        # 1. Bind canonical space
        bind_resp = await client.post(
            "/api/memory/space-guard/bind",
            json={
                "collection": coll,
                "fingerprint": {
                    "provider_id": "openai",
                    "model_name": "text-embedding-3-small",
                    "vector_dimension": 1536,
                    "metric_type": "cosine",
                },
                "total_vectors_indexed": 100,
            },
        )
        assert bind_resp.status_code == 200

        # 2. Dimension mismatch check (1536 vs 1024)
        dim_resp = await client.post(
            "/api/memory/space-guard/validate",
            json={
                "collection": coll,
                "fingerprint": {
                    "provider_id": "ollama",
                    "model_name": "bge-m3",
                    "vector_dimension": 1024,
                    "metric_type": "cosine",
                },
                "auto_bind_if_empty": False,
            },
        )
        assert dim_resp.status_code == 200
        dim_data = dim_resp.json()
        assert dim_data["is_valid"] is False
        assert dim_data["status"] == "dimension_mismatch"
        assert dim_data["recommended_action"] == "reindex_required"
        assert "Dimension mismatch" in dim_data["message"]

        # 3. Model base mismatch check (same 1536 dim, but different model provider)
        base_resp = await client.post(
            "/api/memory/space-guard/validate",
            json={
                "collection": coll,
                "fingerprint": {
                    "provider_id": "cohere",
                    "model_name": "embed-v3",
                    "vector_dimension": 1536,
                    "metric_type": "cosine",
                },
                "auto_bind_if_empty": False,
            },
        )
        assert base_resp.status_code == 200
        base_data = base_resp.json()
        assert base_data["is_valid"] is False
        assert base_data["status"] == "model_base_mismatch"
        assert base_data["recommended_action"] == "reindex_required"
        assert "Model base mismatch" in base_data["message"]


@pytest.mark.asyncio
async def test_space_status_and_reindex_pipeline_api(test_app: FastAPI) -> None:
    """Verify status query and reindexing endpoint workflow."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        coll = "reindex_coll"

        # 1. Status for non-existent space
        stat_resp = await client.get(f"/api/memory/space-guard/status/{coll}")
        assert stat_resp.status_code == 200
        assert stat_resp.json()["has_registered_space"] is False

        # 2. Trigger reindex with sample items
        reindex_resp = await client.post(
            "/api/memory/space-guard/reindex",
            json={
                "collection": coll,
                "target_fingerprint": {
                    "provider_id": "ollama",
                    "model_name": "bge-m3",
                    "vector_dimension": 1024,
                    "metric_type": "cosine",
                },
                "sample_items": ["Doc A", "Doc B", "Doc C"],
            },
        )
        assert reindex_resp.status_code == 200
        reindex_data = reindex_resp.json()
        assert reindex_data["status"] == "completed"
        assert reindex_data["reindexed_count"] == 3

        # 3. Status after reindex
        stat_resp2 = await client.get(f"/api/memory/space-guard/status/{coll}")
        assert stat_resp2.status_code == 200
        stat_data2 = stat_resp2.json()
        assert stat_data2["has_registered_space"] is True
        assert stat_data2["total_vectors_indexed"] == 3
        assert stat_data2["fingerprint"]["vector_dimension"] == 1024
