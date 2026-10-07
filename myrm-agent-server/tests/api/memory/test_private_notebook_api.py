"""[POS]: tests/api/memory/test_private_notebook_api.py
[INPUT]: Isolated FastAPI test application and httpx AsyncClient.
[OUTPUT]: Comprehensive integration tests verifying notes CRUD, search, history recall, and context handover.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.private_notebook_router import (
    router as private_notebook_router,
)
from app.services.memory.private_notebook_service import (
    PrivateNotebookService,
    get_private_notebook_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> PrivateNotebookService:
    """Provides a fresh PrivateNotebookService instance with isolated temporary storage."""
    service = PrivateNotebookService(workspace_dir=tmp_path / "sandbox_workspace")
    return service


@pytest.fixture
def test_app(isolated_service: PrivateNotebookService) -> FastAPI:
    """Creates FastAPI test app overriding get_private_notebook_service with isolated fixture."""
    app = FastAPI()
    app.include_router(private_notebook_router, prefix="/api/memory")
    app.dependency_overrides[get_private_notebook_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_notes_crud_and_search_api(test_app: FastAPI) -> None:
    """Verifies notes creation, appending, retrieval, search, updating, and deletion via API."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Create note
        payload_create = {
            "title": "database_setup",
            "content": "## Step 1\nInitialize SQLite database with WAL mode.",
            "tags": ["db", "sqlite"],
        }
        res_create = await client.post("/api/memory/notebook/notes", json=payload_create)
        assert res_create.status_code == 200
        data_create = res_create.json()
        assert data_create["title"] == "database_setup"
        assert "WAL mode" in data_create["content"]

        # 2. Append to note
        payload_append = {
            "title": "database_setup",
            "content": "## Step 2\nConfigure busy_timeout to 5000ms.",
            "tags": ["db"],
        }
        res_append = await client.post("/api/memory/notebook/notes", json=payload_append)
        assert res_append.status_code == 200
        assert "Step 1" in res_append.json()["content"]
        assert "Step 2" in res_append.json()["content"]

        # 3. List notes
        res_list = await client.get("/api/memory/notebook/notes")
        assert res_list.status_code == 200
        metas = res_list.json()
        assert len(metas) == 1
        assert metas[0]["title"] == "database_setup"

        # 4. Search notes
        res_search = await client.get("/api/memory/notebook/notes/search?q=busy_timeout")
        assert res_search.status_code == 200
        hits = res_search.json()
        assert len(hits) == 1
        assert hits[0]["title"] == "database_setup"
        assert "busy_timeout" in hits[0]["snippet"]

        # 5. Read note
        res_get = await client.get("/api/memory/notebook/notes/database_setup")
        assert res_get.status_code == 200
        assert "WAL mode" in res_get.json()["content"]

        # 6. Rewrite note (human rectification / model overwrite)
        payload_rewrite = {
            "title": "database_setup",
            "content": "## Rectified Step\nMigrated to embedded DuckDB for columnar analytics.",
        }
        res_put = await client.put("/api/memory/notebook/notes/database_setup", json=payload_rewrite)
        assert res_put.status_code == 200
        assert "DuckDB" in res_put.json()["content"]
        assert "WAL mode" not in res_put.json()["content"]

        # 7. Delete note
        res_del = await client.delete("/api/memory/notebook/notes/database_setup")
        assert res_del.status_code == 200
        assert res_del.json()["deleted"] is True

        # Read after delete returns 404
        res_get_deleted = await client.get("/api/memory/notebook/notes/database_setup")
        assert res_get_deleted.status_code == 404


@pytest.mark.asyncio
async def test_history_and_context_handover_api(test_app: FastAPI) -> None:
    """Verifies turn recording, cross-context search, and clean context window rotation."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Record turns
        turn1 = {"role": "user", "content": "Let's investigate the CPU spike on worker 3."}
        turn2 = {"role": "assistant", "content": "Collected profile dump, top consumer is JSON parser."}
        res_t1 = await client.post("/api/memory/notebook/turn", json=turn1)
        res_t2 = await client.post("/api/memory/notebook/turn", json=turn2)
        assert res_t1.status_code == 200
        assert res_t2.status_code == 200

        # Check contexts list
        res_ctxs = await client.get("/api/memory/notebook/history/contexts")
        assert res_ctxs.status_code == 200
        ctx_list = res_ctxs.json()
        assert len(ctx_list) == 1
        active_ctx_id = ctx_list[0]["context_id"]
        assert ctx_list[0]["turn_count"] == 2

        # Check entries under context
        res_entries = await client.get(f"/api/memory/notebook/history/entries/{active_ctx_id}")
        assert res_entries.status_code == 200
        entries = res_entries.json()
        assert len(entries) == 2
        assert "CPU spike" in entries[0]["content"]

        # Search history
        res_hist_search = await client.get("/api/memory/notebook/history/search?q=JSON+parser")
        assert res_hist_search.status_code == 200
        hist_hits = res_hist_search.json()
        assert len(hist_hits) >= 1
        assert "JSON parser" in hist_hits[0]["content"]

        # 2. Model creates a private note before rotating
        await client.post(
            "/api/memory/notebook/notes",
            json={"title": "profiling_findings", "content": "Worker 3 JSON parser bottleneck confirmed."},
        )

        # 3. Rotate context window smoothly
        payload_switch = {
            "summary_reason": "Context nearing token ceiling; rotating to fresh window with profiling_findings preserved.",
        }
        res_switch = await client.post("/api/memory/notebook/new-context", json=payload_switch)
        assert res_switch.status_code == 200
        switch_data = res_switch.json()
        assert switch_data["status"] == "ready"
        assert switch_data["previous_context_id"] == active_ctx_id
        assert switch_data["new_context_id"] != active_ctx_id
        assert switch_data["carried_notes_count"] >= 2  # profiling_findings + context_handovers

        # 4. Verify notes remain accessible after rotation
        res_notes_after = await client.get("/api/memory/notebook/notes")
        assert res_notes_after.status_code == 200
        titles_after = {n["title"] for n in res_notes_after.json()}
        assert "profiling_findings" in titles_after
        assert "context_handovers" in titles_after
