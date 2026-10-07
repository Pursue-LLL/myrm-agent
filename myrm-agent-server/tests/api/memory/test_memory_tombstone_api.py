"""[POS]: tests/api/memory/test_memory_tombstone_api.py
[INPUT]: None.
[OUTPUT]: Isolated integration tests for memory contradiction curation, tombstone recall filtering, and eviction API.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.tombstone import router
from app.services.memory.tombstone import MemoryTombstoneProvider


@pytest.fixture(autouse=True)
def setup_isolated_tombstone_provider(tmp_path: Path):
    db_file = tmp_path / "test_api_tombstone.db"
    MemoryTombstoneProvider.set_custom_db_path(db_file)
    yield
    MemoryTombstoneProvider.reset()


@pytest.mark.asyncio
async def test_memory_tombstone_full_lifecycle_api() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/memory")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Scan and Curate: Contradictory directives
        curate_req = {
            "memories": [
                {
                    "memory_id": "dir_old_comment",
                    "content": "极简代码风格，不要写任何注释",
                    "category": "code_style",
                    "created_at": 100.0,
                    "tags": ["coding"],
                },
                {
                    "memory_id": "dir_new_comment",
                    "content": "为所有核心函数添加详尽注释与docstring",
                    "category": "code_style",
                    "created_at": 200.0,
                    "tags": ["coding"],
                },
            ],
            "auto_tombstone": True,
        }

        resp = await client.post("/api/memory/tombstone/scan-curate", json=curate_req)
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_scanned"] == 2
        assert data["total_contradictions_found"] == 1
        assert data["total_tombstoned"] == 1
        assert len(data["contradictions"]) == 1

        c_pair = data["contradictions"][0]
        assert c_pair["new_memory_id"] == "dir_new_comment"
        assert c_pair["outdated_memory_id"] == "dir_old_comment"

        # 2. Filter Active: Tombstoned item must be blocked
        filter_req = {
            "candidates": [
                {
                    "memory_id": "dir_old_comment",
                    "content": "极简代码风格，不要写任何注释",
                    "category": "code_style",
                    "created_at": 100.0,
                },
                {
                    "memory_id": "dir_new_comment",
                    "content": "为所有核心函数添加详尽注释与docstring",
                    "category": "code_style",
                    "created_at": 200.0,
                },
            ]
        }
        filter_resp = await client.post("/api/memory/tombstone/filter-active", json=filter_req)
        assert filter_resp.status_code == 200
        filter_data = filter_resp.json()
        assert filter_data["total_active"] == 1
        active_ids = [m["memory_id"] for m in filter_data["active_memories"]]
        assert "dir_old_comment" not in active_ids
        assert "dir_new_comment" in active_ids

        # 3. Check Records endpoint
        records_resp = await client.get("/api/memory/tombstone/records")
        assert records_resp.status_code == 200
        records_data = records_resp.json()
        assert records_data["total_records"] >= 1
        rec = next(r for r in records_data["records"] if r["memory_id"] == "dir_old_comment")
        assert rec["state"] == "tombstoned"
        assert rec["superseded_by_id"] == "dir_new_comment"

        # 4. Revive Tombstone
        revive_resp = await client.post(
            "/api/memory/tombstone/revive",
            json={"memory_id": "dir_old_comment"},
        )
        assert revive_resp.status_code == 200
        revive_data = revive_resp.json()
        assert revive_data["success"] is True

        # 5. Verify revival restored active recall status
        filter_resp_2 = await client.post("/api/memory/tombstone/filter-active", json=filter_req)
        assert filter_resp_2.status_code == 200
        active_ids_2 = [m["memory_id"] for m in filter_resp_2.json()["active_memories"]]
        assert "dir_old_comment" in active_ids_2

        # 6. Re-tombstone and Evict
        await client.post("/api/memory/tombstone/scan-curate", json=curate_req)
        evict_resp = await client.post(
            "/api/memory/tombstone/evict",
            json={"memory_ids": ["dir_old_comment"]},
        )
        assert evict_resp.status_code == 200
        assert evict_resp.json()["evicted_count"] == 1

        # Check record after eviction
        records_resp_3 = await client.get("/api/memory/tombstone/records")
        rec_evicted = next(r for r in records_resp_3.json()["records"] if r["memory_id"] == "dir_old_comment")
        assert rec_evicted["state"] == "evicted"
        assert rec_evicted["evicted_at"] is not None
