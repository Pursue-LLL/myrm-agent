"""[POS]: tests/api/memory/test_four_tier_fts_api.py
[INPUT]: Isolated FastAPI test application, AsyncClient, and temporary SQLite storage.
[OUTPUT]: Integration tests verifying four-tier memory CRUD, SQLite FTS5 search, and dream compaction.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.four_tier_fts_router import (
    router as four_tier_fts_router,
)
from app.services.memory.four_tier_fts_service import (
    FourTierFtsService,
    get_four_tier_fts_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> FourTierFtsService:
    """Provides an isolated FourTierFtsService instance backed by temporary storage directory."""
    return FourTierFtsService(base_storage_dir=tmp_path / "four_tier_test")


@pytest.fixture
def test_app(isolated_service: FourTierFtsService) -> FastAPI:
    """Creates a FastAPI test application with dependency overrides."""
    app = FastAPI()
    app.include_router(four_tier_fts_router, prefix="/api/memory")
    app.dependency_overrides[get_four_tier_fts_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_four_tier_memory_crud_api(test_app: FastAPI) -> None:
    """Verifies CRUD operations across all four memory scopes: project, session, progress, global."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Save four items in different tiers
        scopes = [
            ("project", "Repo Structure", "Project root contains core packages.", "proj_1", ""),
            ("session", "User Goal", "User requested automated refactoring.", "proj_1", "sess_1"),
            ("progress", "Step 2 Status", "Step 2 AST parsing is 80% finished.", "proj_1", "sess_1"),
            ("global", "Developer Habit", "Prefers concise commit messages.", "default", ""),
        ]

        saved_ids: list[str] = []
        for scope, title, content, proj, sess in scopes:
            payload = {
                "scope": scope,
                "title": title,
                "content": content,
                "project_hash": proj,
                "session_id": sess,
                "tags": [scope, "automation"],
            }
            res = await client.post("/api/memory/four-tier/items", json=payload)
            assert res.status_code == 200, res.text
            data = res.json()
            assert data["scope"] == scope
            assert data["title"] == title
            assert data["content"] == content
            saved_ids.append(data["item_id"])

        assert len(saved_ids) == 4

        # 2. Get item by ID
        res_get = await client.get(f"/api/memory/four-tier/items/{saved_ids[0]}?project_hash=proj_1")
        assert res_get.status_code == 200
        assert res_get.json()["title"] == "Repo Structure"

        # 3. 404 for unknown item
        res_404 = await client.get("/api/memory/four-tier/items/non_existent_id?project_hash=proj_1")
        assert res_404.status_code == 404

        # 4. List items filtered by scope
        res_list_proj = await client.get("/api/memory/four-tier/items?scope=project&project_hash=proj_1")
        assert res_list_proj.status_code == 200
        proj_items = res_list_proj.json()
        assert len(proj_items) == 1
        assert proj_items[0]["title"] == "Repo Structure"

        # 5. List items filtered by session_id
        res_list_sess = await client.get("/api/memory/four-tier/items?project_hash=proj_1&session_id=sess_1")
        assert res_list_sess.status_code == 200
        sess_items = res_list_sess.json()
        assert len(sess_items) == 2

        # 6. Delete item
        del_res = await client.delete(f"/api/memory/four-tier/items/{saved_ids[0]}?project_hash=proj_1")
        assert del_res.status_code == 200
        assert del_res.json()["deleted"] is True

        # Verify deleted
        verify_del = await client.get(f"/api/memory/four-tier/items/{saved_ids[0]}?project_hash=proj_1")
        assert verify_del.status_code == 404


@pytest.mark.asyncio
async def test_four_tier_fts_search_api(test_app: FastAPI) -> None:
    """Verifies SQLite FTS5 BM25 search across indexed memory scopes."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Populate memories
        await client.post(
            "/api/memory/four-tier/items",
            json={
                "scope": "project",
                "title": "Database Config",
                "content": "PostgreSQL connection pooling pool_size=20 max_overflow=10.",
                "project_hash": "proj_search",
            },
        )
        await client.post(
            "/api/memory/four-tier/items",
            json={
                "scope": "global",
                "title": "Cache Config",
                "content": "Redis distributed cache cluster with TTL 3600 seconds.",
                "project_hash": "proj_search",
            },
        )

        # FTS query for PostgreSQL
        res_pg = await client.get("/api/memory/four-tier/search?query=PostgreSQL&project_hash=proj_search")
        assert res_pg.status_code == 200
        results_pg = res_pg.json()
        assert len(results_pg) == 1
        assert "PostgreSQL" in results_pg[0]["content"]

        # FTS query for Redis
        res_redis = await client.get("/api/memory/four-tier/search?query=Redis&project_hash=proj_search")
        assert res_redis.status_code == 200
        assert len(res_redis.json()) == 1

        # FTS query with scope restriction
        res_filtered = await client.get(
            "/api/memory/four-tier/search?query=Redis&scope=project&project_hash=proj_search"
        )
        assert res_filtered.status_code == 200
        assert len(res_filtered.json()) == 0


@pytest.mark.asyncio
async def test_four_tier_dream_compaction_api(
    test_app: FastAPI, isolated_service: FourTierFtsService
) -> None:
    """Verifies dream compaction merges duplicate fragments and prunes stale progress memories."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        proj_hash = "proj_dream"

        # 1. Insert multiple fragments for the same title
        await client.post(
            "/api/memory/four-tier/items",
            json={
                "scope": "project",
                "title": "Build Notes",
                "content": "Part 1: Installed dependencies via uv.",
                "project_hash": proj_hash,
            },
        )
        await client.post(
            "/api/memory/four-tier/items",
            json={
                "scope": "project",
                "title": "Build Notes",
                "content": "Part 2: Configured ruff and pytest suites.",
                "project_hash": proj_hash,
            },
        )

        # 2. Insert an old progress item directly via engine to simulate 10 days ago
        engine = isolated_service._engine
        from myrm_agent_harness.toolkits.memory import FourTierMemoryItem, MemoryScope

        ten_days_ago = datetime.now(UTC) - timedelta(days=10)
        old_progress = FourTierMemoryItem(
            item_id="prog_old_01",
            scope=MemoryScope.PROGRESS,
            title="Temp Stage",
            content="Old step that finished a long time ago.",
            project_hash=proj_hash,
            session_id="sess_old",
            created_at=ten_days_ago,
            updated_at=ten_days_ago,
        )
        engine.save_item(old_progress)

        # 3. Trigger dream compaction API
        compaction_payload = {
            "project_hash": proj_hash,
            "purge_progress_days": 7,
        }
        res_dream = await client.post("/api/memory/four-tier/dream", json=compaction_payload)
        assert res_dream.status_code == 200, res_dream.text
        report = res_dream.json()
        assert report["merged_items_count"] == 1
        assert report["pruned_items_count"] == 1

        # 4. Check merged Build Notes content
        remaining_items = await client.get(f"/api/memory/four-tier/items?project_hash={proj_hash}")
        assert remaining_items.status_code == 200
        items_data = remaining_items.json()
        assert len(items_data) == 1
        assert "Part 1" in items_data[0]["content"]
        assert "Part 2" in items_data[0]["content"]

        # 5. Check old progress item is gone
        old_item_res = await client.get(f"/api/memory/four-tier/items/prog_old_01?project_hash={proj_hash}")
        assert old_item_res.status_code == 404
