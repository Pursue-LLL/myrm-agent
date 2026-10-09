# [POS]: tests/api/memory/test_ephemeral_delta_api.py
# [INPUT]: app.api.memory.ephemeral_delta_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for Ephemeral Delta Memory Suite (Item 98)

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.ephemeral_delta_router import router as ephemeral_delta_router
from app.services.memory.ephemeral_delta_service import (
    EphemeralDeltaService,
    get_ephemeral_delta_service,
)


@pytest.fixture
def isolated_service() -> EphemeralDeltaService:
    """Provides an isolated in-memory EphemeralDeltaService instance."""
    return EphemeralDeltaService()


@pytest.fixture
def test_app(isolated_service: EphemeralDeltaService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(ephemeral_delta_router, prefix="/api/memory")
    app.dependency_overrides[get_ephemeral_delta_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_record_ephemeral_delta_and_get_active(test_app: FastAPI) -> None:
    """Test recording turn-scoped deltas, LWW deduplication, and snapshot retrieval."""
    session_id = "test-sess-delta-01"

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Record first delta
        payload_1 = {
            "session_id": session_id,
            "target_key": "pkg_manager",
            "content": "Use yarn for installing packages",
            "action": "override",
            "turn_index": 1,
            "source": "user_explicit",
            "confidence": 1.0,
        }
        res_1 = await client.post("/api/memory/ephemeral-delta/record", json=payload_1)
        assert res_1.status_code == 200
        data_1 = res_1.json()
        assert data_1["target_key"] == "pkg_manager"
        assert data_1["content"] == "Use yarn for installing packages"

        # 2. Record second delta on same target_key (LWW override)
        payload_2 = {
            "session_id": session_id,
            "target_key": "pkg_manager",
            "content": "Correction: use pnpm exclusively",
            "action": "override",
            "turn_index": 2,
            "source": "user_explicit",
            "confidence": 1.0,
        }
        res_2 = await client.post("/api/memory/ephemeral-delta/record", json=payload_2)
        assert res_2.status_code == 200

        # 3. Record third delta on distinct key
        payload_3 = {
            "session_id": session_id,
            "target_key": "editor",
            "content": "Neovim only",
            "action": "add_fact",
            "turn_index": 2,
            "source": "user_explicit",
            "confidence": 0.9,
        }
        res_3 = await client.post("/api/memory/ephemeral-delta/record", json=payload_3)
        assert res_3.status_code == 200

        # 4. Fetch active deltas
        active_res = await client.get(f"/api/memory/ephemeral-delta/active/{session_id}")
        assert active_res.status_code == 200
        active_items = active_res.json()
        assert len(active_items) == 2

        by_key = {item["target_key"]: item["content"] for item in active_items}
        assert by_key["pkg_manager"] == "Correction: use pnpm exclusively"
        assert by_key["editor"] == "Neovim only"

        # 5. Fetch snapshot
        snapshot_res = await client.get(f"/api/memory/ephemeral-delta/snapshot/{session_id}")
        assert snapshot_res.status_code == 200
        snapshot_data = snapshot_res.json()
        assert snapshot_data["session_id"] == session_id
        assert len(snapshot_data["active_deltas"]) == 2
        assert not snapshot_data["is_reconciled"]


@pytest.mark.asyncio
async def test_reconcile_ephemeral_session_deltas(test_app: FastAPI) -> None:
    """Test reconciling active transient deltas into durable storage."""
    session_id = "test-sess-reconcile-02"

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Record delta
        payload = {
            "session_id": session_id,
            "target_key": "database",
            "content": "PostgreSQL 16",
            "action": "override",
            "turn_index": 1,
            "source": "agent_inferred",
            "confidence": 0.95,
        }
        rec_res = await client.post("/api/memory/ephemeral-delta/record", json=payload)
        assert rec_res.status_code == 200

        # Reconcile session
        rec_post = await client.post(f"/api/memory/ephemeral-delta/reconcile/{session_id}")
        assert rec_post.status_code == 200
        reconcile_data = rec_post.json()

        assert reconcile_data["session_id"] == session_id
        assert reconcile_data["reconciled_count"] == 1
        assert reconcile_data["overridden_count"] == 0
        assert reconcile_data["persisted_keys"] == ["database"]

        # Confirm buffer is now marked as reconciled
        snapshot_res = await client.get(f"/api/memory/ephemeral-delta/snapshot/{session_id}")
        assert snapshot_res.status_code == 200
        assert snapshot_res.json()["is_reconciled"] is True
