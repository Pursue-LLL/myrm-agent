# [POS]: tests/api/memory/test_hybrid_memory_api.py
# [INPUT]: Isolated FastAPI test application, AsyncClient, and temporary SQLite database file.
# [OUTPUT]: Integration tests verifying FTS5 CRUD, synonym expansion, hybrid search, and telemetry APIs.

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.hybrid_memory_router import router as hybrid_memory_router
from app.services.memory.hybrid_memory_service import (
    HybridMemoryService,
    get_hybrid_memory_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> HybridMemoryService:
    """Provides an isolated HybridMemoryService backed by temporary SQLite DB."""
    db_file = tmp_path / "test_hybrid_api.db"
    return HybridMemoryService(db_path=db_file)


@pytest.fixture
def test_app(isolated_service: HybridMemoryService) -> FastAPI:
    """Creates a FastAPI test application with dependency overrides."""
    app = FastAPI()
    app.include_router(hybrid_memory_router, prefix="/api/memory")
    app.dependency_overrides[get_hybrid_memory_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_insert_get_delete_hybrid_memory_api(test_app: FastAPI) -> None:
    """Verifies storing, fetching, and removing items via REST APIs."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Insert item
        res_insert = await client.post(
            "/api/memory/hybrid/items",
            json={
                "item": {
                    "item_id": "mem_arch_001",
                    "title": "Authentication Architecture",
                    "content": "Mandatory JWT token validation for external endpoints.",
                    "tags": ["auth", "security"],
                    "metadata": {"priority": 1, "tier": "p0"},
                }
            },
        )
        assert res_insert.status_code == 200
        data_ins = res_insert.json()
        assert data_ins["is_success"] is True
        assert data_ins["item_id"] == "mem_arch_001"

        # 2. Get item
        res_get = await client.get("/api/memory/hybrid/items/mem_arch_001")
        assert res_get.status_code == 200
        data_get = res_get.json()
        assert data_get["item_id"] == "mem_arch_001"
        assert data_get["title"] == "Authentication Architecture"
        assert data_get["tags"] == ["auth", "security"]

        # 3. Delete item
        res_del = await client.delete("/api/memory/hybrid/items/mem_arch_001")
        assert res_del.status_code == 200

        # 4. Confirm 404 after deletion
        res_not_found = await client.get("/api/memory/hybrid/items/mem_arch_001")
        assert res_not_found.status_code == 404


@pytest.mark.asyncio
async def test_synonym_registration_and_hybrid_search_api(test_app: FastAPI) -> None:
    """Verifies synonym cluster registration and semantic recall without exact keyword matching."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register a custom domain synonym
        res_syn = await client.post(
            "/api/memory/hybrid/synonyms",
            json={
                "primary_term": "沙箱",
                "synonyms": ["sandbox", "isolation_env", "enclave"],
            },
        )
        assert res_syn.status_code == 200
        assert res_syn.json()["is_success"] is True

        # 2. Insert an item containing "enclave"
        await client.post(
            "/api/memory/hybrid/items",
            json={
                "item": {
                    "item_id": "mem_env_002",
                    "title": "Isolation Enclave Specification",
                    "content": "All untrusted code executes inside an isolated enclave environment.",
                    "tags": ["security"],
                }
            },
        )

        # 3. Search using the term "沙箱" -> should recall the item containing "enclave"
        res_search = await client.post(
            "/api/memory/hybrid/items/search",
            json={"query": "沙箱", "limit": 5, "enable_vector": False},
        )
        assert res_search.status_code == 200
        search_data = res_search.json()
        assert search_data["total_hits"] >= 1
        assert search_data["mode"] == "fts_only"
        assert search_data["results"][0]["item_id"] == "mem_env_002"
        assert any("enclave" in term for term in search_data["results"][0]["matched_terms"])

        # 4. Check telemetry endpoint
        res_stats = await client.get("/api/memory/hybrid/stats")
        assert res_stats.status_code == 200
        stats_data = res_stats.json()
        assert stats_data["total_items"] >= 1
        assert stats_data["synonym_terms_count"] > 0
