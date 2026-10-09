"""[POS]: tests/api/memory/test_competitor_migration_api.py
[INPUT]: None.
[OUTPUT]: Isolated integration tests for competitor memory migration REST endpoints.
"""

import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.migration import router
from app.services.memory.migration import CompetitorMigrationProvider


@pytest.fixture(autouse=True)
def setup_isolated_migration_provider(tmp_path: Path):
    db_file = tmp_path / "test_migration.db"
    CompetitorMigrationProvider.set_custom_db_path(db_file)
    yield
    CompetitorMigrationProvider.reset()


@pytest.mark.asyncio
async def test_detect_artifacts_api(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    # Prepare candidate Hermes file
    hermes_file = tmp_path / "hermes_memories.json"
    hermes_data = [
        {"id": "h-1", "memory": "User prefers dark mode in all IDEs", "created_at": 1700000000}
    ]
    hermes_file.write_text(json.dumps(hermes_data), encoding="utf-8")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            f"/api/memory/migration/detect-artifacts?custom_paths={hermes_file}"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_detected"] >= 1
        artifact = next(a for a in data["artifacts"] if a["artifact_path"] == str(hermes_file))
        assert artifact["source_kind"] == "hermes"
        assert artifact["estimated_entries"] == 1


@pytest.mark.asyncio
async def test_import_file_and_idempotency_api(tmp_path: Path) -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    hermes_file = tmp_path / "hermes_memories.json"
    hermes_data = [
        {"id": "h-101", "memory": "User writes Python with strict typing", "category": "coding"},
        {"id": "h-102", "memory": "Prefers pytest over unittest", "category": "testing"},
    ]
    hermes_file.write_text(json.dumps(hermes_data), encoding="utf-8")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First import
        req_body = {
            "source_kind": "hermes",
            "artifact_path": str(hermes_file),
        }
        resp = await client.post("/api/memory/migration/import-file", json=req_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scanned"] == 2
        assert data["total_imported"] == 2
        assert data["total_skipped_duplicates"] == 0
        assert len(data["imported_entries"]) == 2

        # Second import of same file -> Idempotent skip
        resp2 = await client.post("/api/memory/migration/import-file", json=req_body)
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["total_scanned"] == 2
        assert data2["total_imported"] == 0
        assert data2["total_skipped_duplicates"] == 2


@pytest.mark.asyncio
async def test_import_raw_text_and_history_api() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    openclaw_markdown = """# OpenClaw Memory Dump
- [core] Always write clean, modular software components.
- [habit] Drinks iced latte every morning.
"""

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Import raw text
        req_body = {
            "source_kind": "openclaw",
            "raw_text": openclaw_markdown,
            "source_label": "manual-clipboard-export",
        }
        resp = await client.post("/api/memory/migration/import-text", json=req_body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_scanned"] == 2
        assert data["total_imported"] == 2
        assert len(data["imported_entries"]) == 2

        # Verify history endpoint
        hist_resp = await client.get("/api/memory/migration/history")
        assert hist_resp.status_code == 200
        hist_data = hist_resp.json()
        assert hist_data["total_records"] >= 1
        last_record = hist_data["history"][0]
        assert last_record["source_kind"] == "openclaw"


@pytest.mark.asyncio
async def test_invalid_source_kind_handling() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/memory/migration/import-text",
            json={"source_kind": "non_existent_kind", "raw_text": "hello"},
        )
        assert resp.status_code == 400
        assert "Invalid source_kind" in resp.json()["detail"]
