"""Integration tests for Durable Revision & Concurrent Writes API.

[POS]
Tests verifying durable memory writes, point-in-time MVCC snapshot reads,
authoritative change receipts query, and safe rollbacks.

[INPUT]
- fastapi, httpx.AsyncClient, pytest
- app.api.memory.durable_revision_router (router)
- app.services.memory.durable_revision.provider (reset_durable_revision_suite)

[OUTPUT]
- Test functions covering durable revision API endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.durable_revision_router import (
    router as durable_revision_router,
)
from app.services.memory.durable_revision.provider import (
    reset_durable_revision_suite,
)


@pytest.fixture(autouse=True)
def reset_suite_before_test() -> None:
    """Reset durable revision suite before each test."""
    reset_durable_revision_suite()


@pytest.fixture
def test_app() -> FastAPI:
    """Create FastAPI test application with durable revision router."""
    api_app = FastAPI()
    api_app.include_router(durable_revision_router, prefix="/api/memory")
    return api_app


@pytest.mark.asyncio
async def test_write_memory_mutation_and_read_snapshot(test_app: FastAPI) -> None:
    """Verify durable write returns APPLIED receipt and snapshot reads match."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        write_resp = await client.post(
            "/api/memory/durable-revision/write",
            json={
                "key": "user/profile_preference",
                "content": "Theme: Dark, Language: Python",
                "tags": {"category": "preference", "scope": "global"},
                "expected_revision": None,
            },
        )
        assert write_resp.status_code == 200
        rc_data = write_resp.json()
        assert rc_data["status"] == "APPLIED"
        assert rc_data["canonical_revision"] == 1
        assert rc_data["key"] == "user/profile_preference"
        receipt_id = rc_data["receipt_id"]

        # Read latest snapshot
        snap_resp = await client.get("/api/memory/durable-revision/snapshot/user/profile_preference")
        assert snap_resp.status_code == 200
        snap_data = snap_resp.json()
        assert snap_data["revision"] == 1
        assert snap_data["content"] == "Theme: Dark, Language: Python"
        assert snap_data["tags"] == {"category": "preference", "scope": "global"}
        assert not snap_data["is_tombstone"]

        # Query receipt by ID
        rc_query = await client.get(f"/api/memory/durable-revision/receipt/{receipt_id}")
        assert rc_query.status_code == 200
        assert rc_query.json()["receipt_id"] == receipt_id


@pytest.mark.asyncio
async def test_read_historical_snapshot_and_not_found(test_app: FastAPI) -> None:
    """Verify reading historical revision slices and 404 for missing revisions."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        # Commit two versions
        await client.post(
            "/api/memory/durable-revision/write",
            json={"key": "doc/guide", "content": "Version 1 content"},
        )
        await client.post(
            "/api/memory/durable-revision/write",
            json={"key": "doc/guide", "content": "Version 2 content"},
        )

        # Read historical v1
        v1_resp = await client.get("/api/memory/durable-revision/snapshot/doc/guide?revision=1")
        assert v1_resp.status_code == 200
        assert v1_resp.json()["content"] == "Version 1 content"

        # Read historical v2
        v2_resp = await client.get("/api/memory/durable-revision/snapshot/doc/guide?revision=2")
        assert v2_resp.status_code == 200
        assert v2_resp.json()["content"] == "Version 2 content"

        # Missing revision
        v99_resp = await client.get("/api/memory/durable-revision/snapshot/doc/guide?revision=99")
        assert v99_resp.status_code == 404

        # Missing key
        none_resp = await client.get("/api/memory/durable-revision/snapshot/nonexistent_key")
        assert none_resp.status_code == 404


@pytest.mark.asyncio
async def test_rollback_and_retract(test_app: FastAPI) -> None:
    """Verify rollback to prior revision and retract tombstone publishing."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        key = "config/feature_flags"
        await client.post(
            "/api/memory/durable-revision/write",
            json={"key": key, "content": "feature_a=true"},
        )
        await client.post(
            "/api/memory/durable-revision/write",
            json={"key": key, "content": "feature_a=false"},
        )

        # Rollback to revision 1
        rb_resp = await client.post(
            "/api/memory/durable-revision/rollback",
            json={"key": key, "target_revision": 1},
        )
        assert rb_resp.status_code == 200
        rb_data = rb_resp.json()
        assert rb_data["status"] == "REVERTED"
        assert rb_data["canonical_revision"] == 3

        # Read snapshot after rollback
        snap_rb = await client.get(f"/api/memory/durable-revision/snapshot/{key}")
        assert snap_rb.status_code == 200
        assert snap_rb.json()["content"] == "feature_a=true"

        # Retract key
        retract_resp = await client.post(
            "/api/memory/durable-revision/retract",
            json={"key": key},
        )
        assert retract_resp.status_code == 200
        assert retract_resp.json()["status"] == "SUPERSEDED"
        assert retract_resp.json()["canonical_revision"] == 4

        # Read snapshot after retraction
        snap_retract = await client.get(f"/api/memory/durable-revision/snapshot/{key}")
        assert snap_retract.status_code == 200
        assert snap_retract.json()["is_tombstone"]


@pytest.mark.asyncio
async def test_durable_revision_stats(test_app: FastAPI) -> None:
    """Verify retrieval of operational telemetry statistics."""
    async with AsyncClient(
        transport=ASGITransport(app=test_app), base_url="http://test"
    ) as client:
        await client.post(
            "/api/memory/durable-revision/write",
            json={"key": "stat/test", "content": "sample content"},
        )

        stats_resp = await client.get("/api/memory/durable-revision/stats")
        assert stats_resp.status_code == 200
        st = stats_resp.json()
        assert st["total_receipts"] >= 1
        assert st["applied_receipts"] >= 1
        assert st["total_snapshots"] >= 1
