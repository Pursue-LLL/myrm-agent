"""[POS]: tests/api/memory/test_memory_repair_api.py
[INPUT]: FastAPI TestClient, isolated SQLite connection, and memory repair endpoints.
[OUTPUT]: Pytest integration tests verifying check, heal, prune, and health endpoints.
"""

import sqlite3
import time
from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    CachePreservingCompactionBarrier,
    MemoryRepairService,
)

from app.api.memory.repair import (
    get_memory_repair_service,
)
from app.api.memory.repair import (
    router as repair_router,
)


@pytest.fixture
def isolated_service() -> MemoryRepairService:
    """Create isolated MemoryRepairService backed by temporary SQLite memory database."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE myrm_memories (
            id TEXT PRIMARY KEY,
            content TEXT,
            created_at_epoch REAL,
            last_recalled_at_epoch REAL,
            recall_count INTEGER DEFAULT 0,
            is_pinned INTEGER DEFAULT 0,
            status TEXT DEFAULT 'active'
        )
        """
    )
    cursor.execute(
        """
        CREATE VIRTUAL TABLE myrm_memory_fts USING fts5(
            content,
            content='myrm_memories',
            content_rowid='rowid'
        )
        """
    )
    # Insert initial sample rows
    now_epoch = time.time()
    old_epoch = now_epoch - (45 * 86400.0)
    cursor.execute(
        "INSERT INTO myrm_memories VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("mem-p1", "Always write clean code", old_epoch, old_epoch, 10, 1, "active"),
    )
    cursor.execute(
        "INSERT INTO myrm_memories VALUES (?, ?, ?, ?, ?, ?, ?)",
        ("mem-s1", "Temporary port was 8080", old_epoch, old_epoch, 0, 0, "active"),
    )
    conn.commit()

    barrier = CachePreservingCompactionBarrier()
    return MemoryRepairService(conn=conn, barrier=barrier)


@pytest.fixture
def test_app(isolated_service: MemoryRepairService) -> FastAPI:
    """Create FastAPI test application with injected isolated MemoryRepairService."""
    api_app = FastAPI()
    api_app.include_router(repair_router, prefix="/api/memory")
    api_app.dependency_overrides[get_memory_repair_service] = lambda: isolated_service
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to the isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_repair_check_endpoint(client: AsyncClient) -> None:
    """Verify GET /api/memory/repair/check returns healthy integrity diagnostics."""
    resp = await client.get("/api/memory/repair/check")
    assert resp.status_code == 200
    data = resp.json()
    assert data["db_status"] == "healthy"
    assert data["fts_healthy"] is True
    assert "myrm_memories" in data["table_counts"]


@pytest.mark.asyncio
async def test_repair_heal_endpoint(client: AsyncClient) -> None:
    """Verify POST /api/memory/repair/heal triggers index rebuild and checkpoint."""
    resp = await client.post("/api/memory/repair/heal", json={"force_rebuild": True})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["repaired_items"]) > 0


@pytest.mark.asyncio
async def test_repair_prune_and_health_endpoints(client: AsyncClient) -> None:
    """Verify POST /api/memory/repair/prune archives stale items and health updates."""
    # 1. Prune stale memories
    prune_resp = await client.post(
        "/api/memory/repair/prune",
        json={
            "stale_days_threshold": 30,
            "min_recall_count": 0,
            "decay_rate": 0.05,
            "protect_pinned": True,
            "dry_run": False,
            "table_name": "myrm_memories",
        },
    )
    assert prune_resp.status_code == 200
    prune_data = prune_resp.json()
    assert prune_data["archived_count"] == 1
    assert prune_data["archived_ids"] == ["mem-s1"]
    assert prune_data["protected_count"] == 1

    # 2. Check health after pruning
    health_resp = await client.get("/api/memory/repair/health?table_name=myrm_memories")
    assert health_resp.status_code == 200
    health_data = health_resp.json()
    assert health_data["total_entries"] == 2
    assert health_data["active_entries"] == 1
    assert health_data["stale_entries"] == 0
    assert health_data["overall_health_score"] == 100.0
