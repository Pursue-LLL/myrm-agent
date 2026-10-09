# [POS]: tests/api/memory/test_session_commit_api.py
# [INPUT]: app.api.memory.session_commit_router, isolated FastAPI app
# [OUTPUT]: Integration API tests for SessionCommitTwoPhaseArchiveExtractAndMemoryDiffAuditSuite (Item 106)

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import SessionCommitTwoPhaseEngine

from app.api.memory.session_commit_router import (
    router as session_commit_router,
)
from app.services.memory.session_commit_service import (
    SessionCommitService,
    get_session_commit_service,
)


@pytest.fixture
def test_engine(tmp_path: Path) -> SessionCommitTwoPhaseEngine:
    """Provides an isolated engine storing data inside tmp_path."""
    return SessionCommitTwoPhaseEngine(base_storage_dir=tmp_path / "sessions")


@pytest.fixture
def isolated_service(test_engine: SessionCommitTwoPhaseEngine) -> SessionCommitService:
    """Provides an isolated SessionCommitService instance."""
    return SessionCommitService(engine=test_engine)


@pytest.fixture
def test_app(isolated_service: SessionCommitService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(session_commit_router, prefix="/api/memory")
    app.dependency_overrides[get_session_commit_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_session_commit_two_phase_full_lifecycle_api(test_app: FastAPI) -> None:
    """Validate Phase 1 sync archival, Phase 2 async extraction, and memory_diff audit via REST."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Execute Phase 1 Commit
        commit_payload = {
            "session_id": "sess_api_test_01",
            "messages": [
                {
                    "role": "user",
                    "content": "Please implement safe schema migrations for PostgreSQL.",
                    "tool_calls": [],
                    "tool_results": [],
                    "referenced_uris": [],
                },
                {
                    "role": "assistant",
                    "content": "Schema migration applied with zero downtime.",
                    "tool_calls": [{"tool": "alembic_upgrade", "revision": "head"}],
                    "tool_results": [{"status": "success"}],
                    "referenced_uris": ["file:///workspace/alembic/env.py"],
                },
            ],
            "boundary_kind": "target_completed",
            "metadata": {"env": "staging"},
        }

        res_commit = await client.post("/api/memory/session-commit/commit", json=commit_payload)
        assert res_commit.status_code == 200
        commit_data = res_commit.json()
        assert commit_data["phase1_persisted"] is True
        assert commit_data["archive_id"] == "archive_001"
        assert commit_data["phase2_scheduled"] is True
        task_id = commit_data["task_id"]

        # 2. Get commit task status (Phase 1)
        res_task = await client.get(f"/api/memory/session-commit/tasks/{task_id}")
        assert res_task.status_code == 200
        task_data = res_task.json()
        assert task_data["phase"] == "phase1_sync_archived"
        assert task_data["message_count"] == 2

        # 3. Execute Phase 2 extraction with simulated memory diff items
        diffs = [
            {
                "change_kind": "added",
                "memory_type": "procedure_experience",
                "item_id": "proc_alembic_pg_01",
                "before_summary": None,
                "after_summary": "Zero downtime postgres migration rule",
            },
            {
                "change_kind": "superseded",
                "memory_type": "fact",
                "item_id": "fact_pg_pool_size",
                "before_summary": "pool_size=10",
                "after_summary": "pool_size=20",
            },
        ]
        res_p2 = await client.post(
            f"/api/memory/session-commit/execute-phase2/{task_id}",
            json=diffs,
        )
        assert res_p2.status_code == 200
        p2_data = res_p2.json()
        assert p2_data["phase"] == "phase2_completed"
        assert p2_data["completed_at"] is not None
        assert p2_data["diff_stats"]["total_added"] == 1
        assert p2_data["diff_stats"]["total_superseded"] == 1

        # 4. Fetch memory_diff.json audit
        res_diff = await client.get("/api/memory/session-commit/diff/sess_api_test_01/archive_001")
        assert res_diff.status_code == 200
        diff_data = res_diff.json()
        assert diff_data["session_id"] == "sess_api_test_01"
        assert diff_data["boundary_kind"] == "target_completed"
        assert len(diff_data["changes"]) == 2
        assert diff_data["changes"][0]["change_kind"] == "added"
        assert diff_data["changes"][1]["change_kind"] == "superseded"
        assert diff_data["stats"]["total_added"] == 1

        # 5. List archives
        res_archives = await client.get("/api/memory/session-commit/archives/sess_api_test_01")
        assert res_archives.status_code == 200
        assert res_archives.json() == ["archive_001"]
