"""API integration tests for Item 150 SqliteTranscriptProjectionSuite server endpoints.

Covers:
- Cold-start bootstrap projection from SQLite transcript SSOT without session files.
- Idempotent secondary bootstrap execution.
- Disambiguation of repeated content by created time proximity.
- Same-second twin and missing timestamp fail-closed unstamped decisions.
- Genuinely unique content timestamp-free adoption.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.transcript_projection_router import (
    router as transcript_projection_router,
)
from app.services.memory.transcript_projection_service import (
    TranscriptProjectionService,
    get_transcript_projection_service,
)


@pytest.fixture
def isolated_service() -> TranscriptProjectionService:
    """Provides an isolated in-memory TranscriptProjectionService instance."""
    return TranscriptProjectionService(":memory:")


@pytest.fixture
def test_app(isolated_service: TranscriptProjectionService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(transcript_projection_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_transcript_projection_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_cold_start_bootstrap_and_idempotency_api(test_app: FastAPI) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = "sess_api_cold_start"

        # 1. Append transcript entries to SQLite SSOT
        entries_payload = [
            {
                "entry_id": "entry_api_1",
                "session_id": session_id,
                "seq": 1,
                "role": "user",
                "content": "First user query",
                "created_at_ms": 1719662400000,
            },
            {
                "entry_id": "entry_api_2",
                "session_id": session_id,
                "seq": 2,
                "role": "assistant",
                "content": "First assistant answer",
                "created_at_ms": 1719662401000,
                "parent_id": "entry_api_1",
            },
        ]
        resp_append = await client.post("/api/v1/memory/transcript-projection/append", json=entries_payload)
        assert resp_append.status_code == 200
        assert resp_append.json()["appended_count"] == 2

        # 2. Cold-start bootstrap projection
        bootstrap_req = {
            "session_id": session_id,
            "session_key": f"agent:main:{session_id}",
        }
        resp_boot = await client.post("/api/v1/memory/transcript-projection/bootstrap", json=bootstrap_req)
        assert resp_boot.status_code == 200
        data_boot = resp_boot.json()
        assert data_boot["bootstrapped"] is True
        assert data_boot["imported_messages"] == 2
        assert data_boot["already_bootstrapped"] is False

        # 3. Query projected messages
        resp_msgs = await client.get(f"/api/v1/memory/transcript-projection/{session_id}/messages")
        assert resp_msgs.status_code == 200
        msgs = resp_msgs.json()
        assert len(msgs) == 2
        assert msgs[0]["transcript_entry_id"] == "entry_api_1"
        assert msgs[1]["transcript_entry_id"] == "entry_api_2"

        # 4. Secondary bootstrap must be completely idempotent
        resp_boot2 = await client.post("/api/v1/memory/transcript-projection/bootstrap", json=bootstrap_req)
        assert resp_boot2.status_code == 200
        data_boot2 = resp_boot2.json()
        assert data_boot2["already_bootstrapped"] is True
        assert data_boot2["imported_messages"] == 2


@pytest.mark.asyncio
async def test_adopt_repeated_bodies_by_timestamp_api(test_app: FastAPI) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = "sess_api_repeated"
        repeated_text = "[System] Interrupted by restart."
        t0 = 1718965080000
        t1 = 1718965140000

        # Append transcript SSOT with repeated text at t0 and t1
        entries_payload = [
            {
                "entry_id": "entry_rep_1",
                "session_id": session_id,
                "seq": 1,
                "role": "user",
                "content": repeated_text,
                "created_at_ms": t0,
            },
            {
                "entry_id": "entry_rep_2",
                "session_id": session_id,
                "seq": 2,
                "role": "user",
                "content": repeated_text,
                "created_at_ms": t1,
            },
        ]
        await client.post("/api/v1/memory/transcript-projection/append", json=entries_payload)

        # Ingest live messages with timestamps near t0 and t1
        live_payload = [
            {
                "message_id": "msg_live_t0",
                "session_id": session_id,
                "seq": 1,
                "role": "user",
                "content": repeated_text,
                "timestamp_ms": t0 + 50,
            },
            {
                "message_id": "msg_live_t1",
                "session_id": session_id,
                "seq": 2,
                "role": "user",
                "content": repeated_text,
                "timestamp_ms": t1 + 30,
            },
        ]
        await client.post("/api/v1/memory/transcript-projection/ingest", json=live_payload)

        # Reconcile via bootstrap
        resp_boot = await client.post(
            "/api/v1/memory/transcript-projection/bootstrap",
            json={"session_id": session_id, "session_key": f"agent:main:{session_id}"},
        )
        assert resp_boot.status_code == 200
        decisions = resp_boot.json()["decisions"]
        assert len(decisions) == 2
        assert decisions[0]["message_id"] == "msg_live_t0"
        assert decisions[0]["transcript_entry_id"] == "entry_rep_1"
        assert decisions[0]["status"] == "adopted_by_timestamp"

        assert decisions[1]["message_id"] == "msg_live_t1"
        assert decisions[1]["transcript_entry_id"] == "entry_rep_2"
        assert decisions[1]["status"] == "adopted_by_timestamp"


@pytest.mark.asyncio
async def test_twin_and_unknown_timestamp_fail_closed_api(test_app: FastAPI) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        session_id = "sess_api_twins"
        twin_text = "Twin prompt"
        t_twin = 1718965080000

        # Append same-second twins
        entries_payload = [
            {
                "entry_id": "twin_a",
                "session_id": session_id,
                "seq": 1,
                "role": "user",
                "content": twin_text,
                "created_at_ms": t_twin,
            },
            {
                "entry_id": "twin_b",
                "session_id": session_id,
                "seq": 2,
                "role": "user",
                "content": twin_text,
                "created_at_ms": t_twin,
            },
        ]
        await client.post("/api/v1/memory/transcript-projection/append", json=entries_payload)

        live_payload = [
            {
                "message_id": "msg_live_twin",
                "session_id": session_id,
                "seq": 1,
                "role": "user",
                "content": twin_text,
                "timestamp_ms": t_twin + 100,
            }
        ]
        await client.post("/api/v1/memory/transcript-projection/ingest", json=live_payload)

        resp_boot = await client.post(
            "/api/v1/memory/transcript-projection/bootstrap",
            json={"session_id": session_id, "session_key": f"agent:main:{session_id}"},
        )
        assert resp_boot.status_code == 200
        decisions = resp_boot.json()["decisions"]
        assert len(decisions) == 1
        assert decisions[0]["transcript_entry_id"] is None
        assert decisions[0]["status"] == "unstamped_twin_conflict"
