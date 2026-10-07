# [POS]: tests/api/memory/test_markdown_curator_api.py
# [INPUT]: app.api.memory.markdown_curator_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for HumanReadableMarkdownBidiSyncAndMemoryCuratorStudioSuite (Item 101)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.markdown_curator_router import router as markdown_curator_router
from app.services.memory.markdown_curator_service import (
    MarkdownCuratorService,
    get_markdown_curator_service,
)


@pytest.fixture
def isolated_service() -> MarkdownCuratorService:
    """Provides an isolated in-memory MarkdownCuratorService instance."""
    return MarkdownCuratorService()


@pytest.fixture
def test_app(isolated_service: MarkdownCuratorService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(markdown_curator_router, prefix="/api/memory")
    app.dependency_overrides[get_markdown_curator_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_curator_crud_and_audit_api(test_app: FastAPI) -> None:
    """Validate creating, auditing, updating, and erasing memory entries via REST APIs."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create a low-confidence candidate (should trigger anti-misremembering gate)
        create_payload = {
            "category": "preference",
            "title": "Editor Theme",
            "content": "User prefers dark Tokyo Night theme",
            "confidence": 0.65,
            "status": "confirmed",
            "tags": ["ui", "editor"],
        }
        res1 = await client.post("/api/memory/curator/entries", json=create_payload)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["status"] == "pending_confirmation"
        entry_id = data1["entry_id"]

        # 2. Human audit: approve entry
        audit_payload = {"is_approved": True}
        res2 = await client.post(f"/api/memory/curator/entries/{entry_id}/audit", json=audit_payload)
        assert res2.status_code == 200
        data2 = res2.json()
        assert data2["status"] == "confirmed"

        # 3. Update entry content
        update_payload = {
            "content": "User prefers Catppuccin Mocha theme instead",
            "tags": ["ui", "editor", "theme"],
        }
        res3 = await client.put(f"/api/memory/curator/entries/{entry_id}", json=update_payload)
        assert res3.status_code == 200
        data3 = res3.json()
        assert "Catppuccin" in data3["content"]
        assert len(data3["tags"]) == 3

        # 4. Check summary
        sum_res = await client.get("/api/memory/curator/summary")
        assert sum_res.status_code == 200
        sum_data = sum_res.json()
        assert sum_data["total_entries"] == 1
        assert sum_data["confirmed_count"] == 1
        assert sum_data["categories_breakdown"]["preference"] == 1

        # 5. One-click privacy wipe
        del_res = await client.delete(f"/api/memory/curator/entries/{entry_id}?hard_erase=true")
        assert del_res.status_code == 200
        assert del_res.json()["is_success"] is True

        # 6. Verify entry no longer exists
        get_res = await client.get(f"/api/memory/curator/entries/{entry_id}")
        assert get_res.status_code == 404


@pytest.mark.asyncio
async def test_curator_markdown_export_and_bidi_sync_api(test_app: FastAPI) -> None:
    """Validate export to Markdown and synchronization from modified Markdown documents."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Seed two items
        p1 = {
            "category": "fact",
            "title": "Backend Port",
            "content": "Server listens on port 8000",
            "confidence": 1.0,
            "status": "confirmed",
        }
        p2 = {
            "category": "procedure",
            "title": "Deploy Step",
            "content": "Run docker compose up -d",
            "confidence": 0.9,
            "status": "confirmed",
        }
        res_p1 = await client.post("/api/memory/curator/entries", json=p1)
        res_p2 = await client.post("/api/memory/curator/entries", json=p2)
        assert res_p1.status_code == 200
        assert res_p2.status_code == 200
        id1 = res_p1.json()["entry_id"]
        id2 = res_p2.json()["entry_id"]

        # 2. Export to Markdown
        export_res = await client.get("/api/memory/curator/export")
        assert export_res.status_code == 200
        md_text = export_res.text
        assert "## Facts" in md_text
        assert "## Procedures" in md_text
        assert id1 in md_text
        assert id2 in md_text

        # 3. Simulate human modification in workspace Markdown:
        # - modify id1 content
        # - delete id2
        # - add new entry id-user-new
        modified_md = f"""---
title: Workspace Memory Mirror
---
# Workspace Memory Mirror

## Facts

- [x] **Backend Port** (id: {id1}, confidence: 1.00): Server listens on port 8080 (updated)

## Preferences

- [x] **Language** (id: id-user-new, confidence: 1.00): Always answer in concise Chinese
"""
        sync_payload = {
            "markdown_text": modified_md,
            "hard_delete": False,
        }
        sync_res = await client.post("/api/memory/curator/sync", json=sync_payload)
        assert sync_res.status_code == 200
        sync_data = sync_res.json()

        assert sync_data["added_count"] == 1
        assert sync_data["added_entries"][0]["entry_id"] == "id-user-new"

        assert sync_data["updated_count"] == 1
        assert sync_data["updated_entries"][0]["entry_id"] == id1
        assert "8080" in sync_data["updated_entries"][0]["content"]

        assert sync_data["deleted_count"] == 1
        assert id2 in sync_data["deleted_entry_ids"]

        # 4. Verify in-memory state reflects the sync
        get_updated = await client.get(f"/api/memory/curator/entries/{id1}")
        assert "8080" in get_updated.json()["content"]

        get_deleted = await client.get(f"/api/memory/curator/entries/{id2}")
        assert get_deleted.json()["status"] == "archived"
