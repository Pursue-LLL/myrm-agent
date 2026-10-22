"""Tests for OmniReference HTTP REST API and Service.

[INPUT]
- app.api.context.omni_reference::router
- app.services.context.omni_reference::OmniReferenceResolverService
- httpx::AsyncClient

[OUTPUT]
- Unit and endpoint tests verifying 5-dimensional search and slice expansion

[POS]
Unit test suite under tests/api/context/.
"""

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.context.omni_reference import router


@pytest.fixture
def app() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1/context")
    return test_app


@pytest.mark.asyncio
async def test_search_reference_entities_all_dimensions(app: FastAPI) -> None:
    """Verify searching without dimension filter returns entities across multiple dimensions."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/context/reference/search?q=")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) > 0

        dims = {item["dimension"] for item in data}
        assert "agent" in dims
        assert "artifact" in dims
        assert "task" in dims


@pytest.mark.asyncio
async def test_search_reference_entities_by_specific_dimension(app: FastAPI) -> None:
    """Verify searching with dimension filter only returns entities of that dimension."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/context/reference/search?dimension=task&q=context")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) >= 1
        for item in data:
            assert item["dimension"] == "task"
            assert "context" in item["target_id"].lower() or "context" in item["label"].lower()


@pytest.mark.asyncio
async def test_resolve_context_slice_session(app: FastAPI) -> None:
    """Verify resolving context slice for a session extracts bounded slice and provenance uri."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "dimension": "session",
            "target_id": "sess_db_optimization",
            "label": "数据库连接池压测排查",
        }
        resp = await client.post("/api/v1/context/reference/slice", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["dimension"] == "session"
        assert data["target_id"] == "sess_db_optimization"
        assert data["label"] == "数据库连接池压测排查"
        assert "Database pooling" in data["content_slice"]
        assert data["provenance_uri"] == "myrm://session/sess_db_optimization"
        assert data["token_estimate"] >= 1
        assert data["is_truncated"] is False


@pytest.mark.asyncio
async def test_resolve_context_slice_artifact(app: FastAPI) -> None:
    """Verify resolving context slice for an artifact."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "dimension": "artifact",
            "target_id": "art_schema_diagram",
            "label": "架构设计图 ER",
        }
        resp = await client.post("/api/v1/context/reference/slice", json=payload)
        assert resp.status_code == 200
        data = resp.json()["data"]

        assert data["dimension"] == "artifact"
        assert data["target_id"] == "art_schema_diagram"
        assert data["provenance_uri"] == "myrm://artifact/art_schema_diagram"
