"""API integration tests for Item 149 SafeEpisodicForgetSuite server endpoints.

[INPUT]
- app.api.memory.safe_forget_router, FastAPI app, SafeForgetService.

[OUTPUT]
- Integration API tests validating parent probing, safe episodic forgetting, and audit inspection.

[POS]
- Server-side REST API tests for Item 149 SafeEpisodicForgetSuite.
"""

from __future__ import annotations

import time

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.memory.safe_forget_router import router as safe_forget_router
from app.services.memory.safe_forget_service import (
    SafeForgetService,
    get_safe_forget_service,
)


@pytest.fixture
def isolated_service() -> SafeForgetService:
    """Provides an isolated in-memory SafeForgetService instance."""
    return SafeForgetService(":memory:")


@pytest.fixture
def test_app(isolated_service: SafeForgetService) -> FastAPI:
    """Creates a lightweight test FastAPI application with dependency overrides."""
    app = FastAPI()
    app.include_router(safe_forget_router, prefix="/api/v1/memory")
    app.dependency_overrides[get_safe_forget_service] = lambda: isolated_service
    return app


@pytest.mark.asyncio
async def test_probe_memory_parents_api(test_app: FastAPI, isolated_service: SafeForgetService) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Non-existent memory
        resp = await client.post(
            "/api/v1/memory/episodic-forget/probe",
            params={"memory_id": "non_existent", "caller_session_id": "sess_1"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["episodic_exists"] is False
        assert data["authorized"] is False

        # 2. Existing memory with competing working parent
        conn = isolated_service.store.get_connection()
        conn.execute(
            "INSERT INTO episodic_memory (id, session_id, scope, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            ("mem_probe", "sess_1", "session", "Episodic fact", time.time()),
        )
        conn.execute(
            "INSERT INTO working_memory (id, session_id, content, timestamp) VALUES (?, ?, ?, ?)",
            ("mem_probe", "sess_1", "Working fact", time.time()),
        )

        resp2 = await client.post(
            "/api/v1/memory/episodic-forget/probe",
            params={"memory_id": "mem_probe", "caller_session_id": "sess_1"},
        )
        assert resp2.status_code == 200
        data2 = resp2.json()
        assert data2["episodic_exists"] is True
        assert data2["authorized"] is True
        assert data2["has_competing_parents"] is True
        assert "working" in data2["competing_tiers"]


@pytest.mark.asyncio
async def test_execute_safe_forget_success_and_shared_retention_api(
    test_app: FastAPI, isolated_service: SafeForgetService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conn = isolated_service.store.get_connection()
        # Seed episodic row and shared children
        conn.execute(
            "INSERT INTO episodic_memory (id, session_id, scope, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            ("mem_retain", "sess_alpha", "session", "Important insight", time.time()),
        )
        conn.execute(
            "INSERT INTO annotations (id, memory_id, note) VALUES (?, ?, ?)",
            ("ann_1", "mem_retain", "User pinned note"),
        )
        # Seed competing working memory parent
        conn.execute(
            "INSERT INTO working_memory (id, session_id, content, timestamp) VALUES (?, ?, ?, ?)",
            ("mem_retain", "sess_alpha", "Working version", time.time()),
        )

        payload = {
            "memory_id": "mem_retain",
            "caller_session_id": "sess_alpha",
            "reason": "Forget test with shared retention",
        }
        resp = await client.post("/api/v1/memory/episodic-forget/execute", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["retained_shared_children"] is True
        assert data["deleted_child_tables"] == []

        # Verify episodic row deleted, but annotation preserved
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodic_memory WHERE id = 'mem_retain'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM annotations WHERE memory_id = 'mem_retain'")
        assert cur.fetchone()[0] == 1


@pytest.mark.asyncio
async def test_execute_safe_forget_unauthorized_403_api(
    test_app: FastAPI, isolated_service: SafeForgetService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conn = isolated_service.store.get_connection()
        conn.execute(
            "INSERT INTO episodic_memory (id, session_id, scope, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            ("mem_private", "owner_sess", "session", "Private detail", time.time()),
        )

        payload = {
            "memory_id": "mem_private",
            "caller_session_id": "attacker_sess",
            "allow_global": True,
            "reason": "Attempted unauthorized deletion",
        }
        resp = await client.post("/api/v1/memory/episodic-forget/execute", json=payload)
        assert resp.status_code == 403
        assert "Unauthorized" in resp.json()["detail"]

        # Verify row survived
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM episodic_memory WHERE id = 'mem_private'")
        assert cur.fetchone()[0] == 1


@pytest.mark.asyncio
async def test_execute_safe_forget_cascade_and_audit_api(
    test_app: FastAPI, isolated_service: SafeForgetService
) -> None:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        conn = isolated_service.store.get_connection()
        conn.execute(
            "INSERT INTO episodic_memory (id, session_id, scope, content, timestamp) VALUES (?, ?, ?, ?, ?)",
            ("mem_cascade", "sess_beta", "session", "Isolated episodic row", time.time()),
        )
        conn.execute(
            "INSERT INTO annotations (id, memory_id, note) VALUES (?, ?, ?)",
            ("ann_cas", "mem_cascade", "Child note to delete"),
        )
        conn.execute(
            "INSERT INTO gists (id, memory_id, gist) VALUES (?, ?, ?)",
            ("gist_cas", "mem_cascade", "Child gist to delete"),
        )

        payload = {
            "memory_id": "mem_cascade",
            "caller_session_id": "sess_beta",
            "reason": "Permanent user requested deletion",
        }
        resp = await client.post("/api/v1/memory/episodic-forget/execute", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["deleted"] is True
        assert data["retained_shared_children"] is False
        assert "annotations" in data["deleted_child_tables"]
        assert "gists" in data["deleted_child_tables"]

        # Child rows must be deleted
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM annotations WHERE memory_id = 'mem_cascade'")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT COUNT(*) FROM gists WHERE memory_id = 'mem_cascade'")
        assert cur.fetchone()[0] == 0

        # Test audit endpoint
        audit_resp = await client.get("/api/v1/memory/episodic-forget/audit")
        assert audit_resp.status_code == 200
        audit_list = audit_resp.json()
        assert len(audit_list) >= 1
        found = [ev for ev in audit_list if ev["memory_id"] == "mem_cascade"]
        assert len(found) == 1
        assert found[0]["event_name"] == "MEMORY_INVALIDATED"
        assert found[0]["tier"] == "episodic"
