"""[POS]: tests/api/memory/test_revocable_provenance_api.py
[INPUT]: Isolated FastAPI test application, AsyncClient, and temporary storage directories.
[OUTPUT]: Integration tests verifying provenance memory creation, bidirectional lookups, atomic forget, and dream diary recording.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.revocable_provenance_router import (
    router as revocable_provenance_router,
)
from app.services.memory.revocable_provenance_service import (
    RevocableProvenanceService,
    get_revocable_provenance_service,
)


@pytest.fixture
def isolated_service(tmp_path: Path) -> RevocableProvenanceService:
    """Provides an isolated RevocableProvenanceService instance with temporary disk storage."""
    service = RevocableProvenanceService(workspace_dir=tmp_path / "provenance_workspace")
    return service


@pytest.fixture
def test_app(isolated_service: RevocableProvenanceService) -> FastAPI:
    """Creates a FastAPI test app with dependency override for RevocableProvenanceService."""
    app = FastAPI()
    app.include_router(revocable_provenance_router, prefix="/api/memory")
    app.dependency_overrides[get_revocable_provenance_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_provenance_memory_crud_and_bidirectional_lookup_api(test_app: FastAPI) -> None:
    """Verifies creating memories with provenance and looking them up by memory_id, session_id, and message_id."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Save two provenance-qualified memories
        payload1 = {
            "memory_id": "mem_arch_001",
            "statement": "Use hexagonal architecture for core domain services.",
            "category": "architecture_pattern",
            "session_id": "session_project_x",
            "message_id": "msg_turn_3",
            "turn_index": 3,
            "quote_snippet": "Let's stick to hexagonal architecture so business logic remains pure.",
            "confidence_score": 0.98,
        }
        res1 = await client.post("/api/memory/provenance/memories", json=payload1)
        assert res1.status_code == 200
        data1 = res1.json()
        assert data1["memory_id"] == "mem_arch_001"
        assert data1["provenance"]["session_id"] == "session_project_x"
        assert data1["is_revoked"] is False

        payload2 = {
            "memory_id": "mem_arch_002",
            "statement": "Enforce strict zero Any type hint policy across python codebases.",
            "category": "type_safety",
            "session_id": "session_project_x",
            "message_id": "msg_turn_7",
            "turn_index": 7,
            "quote_snippet": "Zero Any in type hints is a non-negotiable rule.",
            "confidence_score": 1.0,
        }
        res2 = await client.post("/api/memory/provenance/memories", json=payload2)
        assert res2.status_code == 200

        # 2. Lookup single memory by ID
        res_get = await client.get("/api/memory/provenance/memories/mem_arch_001")
        assert res_get.status_code == 200
        assert res_get.json()["statement"] == payload1["statement"]

        # 3. Lookup 404 for non-existent memory
        res_not_found = await client.get("/api/memory/provenance/memories/ghost_id")
        assert res_not_found.status_code == 404

        # 4. Bidirectional lookup by session_id
        res_by_session = await client.get("/api/memory/provenance/memories/session/session_project_x")
        assert res_by_session.status_code == 200
        sess_items = res_by_session.json()
        assert len(sess_items) == 2
        assert sess_items[0]["memory_id"] == "mem_arch_001"
        assert sess_items[1]["memory_id"] == "mem_arch_002"

        # 5. Lookup by message_id
        res_by_msg = await client.get("/api/memory/provenance/memories/message/msg_turn_7")
        assert res_by_msg.status_code == 200
        msg_items = res_by_msg.json()
        assert len(msg_items) == 1
        assert msg_items[0]["memory_id"] == "mem_arch_002"


@pytest.mark.asyncio
async def test_atomic_memory_forget_and_anti_resurrection_api(test_app: FastAPI) -> None:
    """Verifies atomic memory forget, transcript preservation, and anti-resurrection exclusion gate."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Save candidate memory
        payload = {
            "memory_id": "mem_flawed_pref",
            "statement": "Omit integration tests for internal CLI tools.",
            "category": "testing_bias",
            "session_id": "session_cli_dev",
            "message_id": "msg_turn_12",
            "turn_index": 12,
            "quote_snippet": "CLI tools don't need integration tests, unit tests are enough.",
            "confidence_score": 0.85,
        }
        res_save = await client.post("/api/memory/provenance/memories", json=payload)
        assert res_save.status_code == 200

        # 2. Atomic memory forget
        reason_str = "User corrected: CLI tools must include integration tests."
        res_forget = await client.delete(
            "/api/memory/provenance/memories/mem_flawed_pref/forget",
            params={"reason": reason_str},
        )
        assert res_forget.status_code == 200
        forget_data = res_forget.json()
        assert forget_data["revoked"] is True
        assert forget_data["transcript_intact"] is True
        assert forget_data["source_session_id"] == "session_cli_dev"

        # 3. Memory list should exclude revoked item by default
        res_list = await client.get("/api/memory/provenance/memories")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 0

        # Memory list with include_revoked=True should include it
        res_list_all = await client.get("/api/memory/provenance/memories?include_revoked=true")
        assert res_list_all.status_code == 200
        assert len(res_list_all.json()) == 1
        assert res_list_all.json()[0]["is_revoked"] is True

        # 4. Anti-resurrection check: attempting to re-save the same statement for same source message must fail
        res_resurrect = await client.post("/api/memory/provenance/memories", json=payload)
        assert res_resurrect.status_code == 400
        assert "tombstone exclusion" in res_resurrect.json()["detail"]


@pytest.mark.asyncio
async def test_dream_diary_record_and_inspection_api(test_app: FastAPI) -> None:
    """Verifies logging background memory consolidation cycles and inspecting dream history."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Log dream cycle 1
        d1 = {
            "agent_id": "agent_librarian",
            "scanned_turns": 50,
            "promoted_memory_ids": ["mem_001", "mem_002"],
            "pruned_duplicates_count": 5,
            "duration_ms": 150.2,
            "status": "completed",
            "notes": "Nightly memory distillation across developer chat threads.",
        }
        res_d1 = await client.post("/api/memory/provenance/dream-diaries", json=d1)
        assert res_d1.status_code == 200
        data_d1 = res_d1.json()
        assert data_d1["agent_id"] == "agent_librarian"
        assert data_d1["scanned_turns"] == 50
        assert len(data_d1["promoted_memory_ids"]) == 2

        # 2. Log dream cycle 2 for different agent
        d2 = {
            "agent_id": "agent_coder",
            "scanned_turns": 20,
            "promoted_memory_ids": ["mem_003"],
            "pruned_duplicates_count": 1,
            "duration_ms": 60.0,
            "status": "completed",
            "notes": "Refined coding conventions from git diff interactions.",
        }
        res_d2 = await client.post("/api/memory/provenance/dream-diaries", json=d2)
        assert res_d2.status_code == 200

        # 3. List all dream diaries
        res_list = await client.get("/api/memory/provenance/dream-diaries")
        assert res_list.status_code == 200
        assert len(res_list.json()) == 2

        # 4. List dream diaries filtered by agent
        res_filtered = await client.get("/api/memory/provenance/dream-diaries?agent_id=agent_librarian")
        assert res_filtered.status_code == 200
        assert len(res_filtered.json()) == 1
        assert res_filtered.json()[0]["agent_id"] == "agent_librarian"
