"""[POS]: tests/api/memory/test_disk_reconciliation_api.py
[INPUT]: Isolated FastAPI test application, AsyncClient, and temporary Markdown files on disk.
[OUTPUT]: Integration tests verifying write-gate policies, bi-directional reconciliation sync, and FTS search.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.disk_reconciliation_router import (
    router as disk_reconciliation_router,
)
from app.services.memory.disk_reconciliation_service import (
    DiskReconciliationService,
    get_disk_reconciliation_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> DiskReconciliationService:
    """Provides an isolated DiskReconciliationService backed by temporary SQLite DB."""
    db_file = tmp_path / "test_reconcile_api.db"
    return DiskReconciliationService(db_path=db_file)


@pytest.fixture
def test_app(isolated_service: DiskReconciliationService) -> FastAPI:
    """Creates a FastAPI test application with dependency overrides."""
    app = FastAPI()
    app.include_router(disk_reconciliation_router, prefix="/api/memory")
    app.dependency_overrides[get_disk_reconciliation_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_write_gate_policy_api(test_app: FastAPI) -> None:
    """Verifies querying and updating memory write-gate policies."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Default gate is enabled
        res_check = await client.get("/api/memory/reconciliation/write-gate")
        assert res_check.status_code == 200
        data_default = res_check.json()
        assert data_default["is_allowed"] is True
        assert data_default["policy"] == "enabled"

        # 2. Update to read-only policy
        res_set = await client.post(
            "/api/memory/reconciliation/write-gate",
            json={"policy": "read_only_session"},
        )
        assert res_set.status_code == 200
        data_ro = res_set.json()
        assert data_ro["is_allowed"] is False
        assert data_ro["policy"] == "read_only_session"

        # 3. Reject invalid policy with 400
        res_bad = await client.post(
            "/api/memory/reconciliation/write-gate",
            json={"policy": "invalid_mode"},
        )
        assert res_bad.status_code == 400

        # 4. Restore enabled policy
        res_restore = await client.post(
            "/api/memory/reconciliation/write-gate",
            json={"policy": "enabled"},
        )
        assert res_restore.status_code == 200
        assert res_restore.json()["is_allowed"] is True


@pytest.mark.asyncio
async def test_disk_reconciliation_sync_and_search_api(
    test_app: FastAPI, tmp_path: Path
) -> None:
    """Verifies Direction A incremental indexing and Direction B pruning of deleted files via API."""
    notes_dir = tmp_path / "project_notes"
    notes_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create two physical markdown notes
    note1 = notes_dir / "architecture.md"
    note1.write_text("# System Architecture\nUse hexagonal ports and adapters pattern.", encoding="utf-8")

    note2 = notes_dir / "deployment.md"
    note2.write_text("# Deployment Playbook\nZero-downtime rolling update via k8s deployment.", encoding="utf-8")

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 2. Trigger reconciliation pass (Direction A)
        res_sync = await client.post(
            "/api/memory/reconciliation/sync",
            json={"roots": [str(notes_dir)]},
        )
        assert res_sync.status_code == 200
        report = res_sync.json()
        assert report["status"] == "completed"
        assert report["scanned_disk_files_count"] == 2
        assert report["indexed_or_updated_count"] == 2
        assert report["pruned_dead_rows_count"] == 0

        # 3. Full-text search for deployment
        res_search = await client.get("/api/memory/reconciliation/search?query=deployment")
        assert res_search.status_code == 200
        hits = res_search.json()
        assert len(hits) == 1
        assert "Deployment Playbook" in hits[0]["title"]

        # 4. Fetch reconciliation stats
        res_stats = await client.get("/api/memory/reconciliation/stats")
        assert res_stats.status_code == 200
        assert res_stats.json()["total_indexed_files"] == 2

        # 5. Delete deployment.md on physical disk (Direction B testing)
        note2.unlink()
        assert not note2.exists()

        # 6. Re-trigger reconciliation sync
        res_sync2 = await client.post(
            "/api/memory/reconciliation/sync",
            json={"roots": [str(notes_dir)]},
        )
        assert res_sync2.status_code == 200
        report2 = res_sync2.json()
        assert report2["scanned_disk_files_count"] == 1
        assert report2["indexed_or_updated_count"] == 0
        assert report2["pruned_dead_rows_count"] == 1

        # 7. Search for deployment note confirms it is completely removed
        res_search_purged = await client.get("/api/memory/reconciliation/search?query=deployment")
        assert res_search_purged.status_code == 200
        assert len(res_search_purged.json()) == 0

        # 8. Remaining note is still indexed
        res_stats2 = await client.get("/api/memory/reconciliation/stats")
        assert res_stats2.json()["total_indexed_files"] == 1
