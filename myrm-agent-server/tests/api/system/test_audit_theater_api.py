"""
[INPUT]:
- httpx, ASGITransport
- app.api.system.audit_theater_api::router

[OUTPUT]:
- Pytest verification for lie-immune in-conversation audit theater and resource-level data access ledger REST endpoints.

[POS]:
tests/api/system/test_audit_theater_api.py — 用户面审计剧场与数据访问台账 API 单元测试。
"""

from collections.abc import AsyncGenerator
from fastapi import FastAPI
import httpx
from httpx import ASGITransport
import pytest

from app.api.system.audit_theater_api import router as audit_router

test_app = FastAPI()
test_app.include_router(audit_router, prefix="/api/v1/system")


@pytest.fixture
async def async_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    async with httpx.AsyncClient(
        transport=ASGITransport(app=test_app),
        base_url="http://testserver",
        headers={"Content-Type": "application/json"},
    ) as client:
        yield client


@pytest.mark.asyncio
async def test_audit_theater_api_lifecycle(async_client: httpx.AsyncClient) -> None:
    session_id = "sess-theater-001"

    # 1. Reset state
    reset_resp = await async_client.post("/api/v1/system/audit-theater/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json() == {"status": "reset"}

    # 2. Record resource accesses
    r1 = await async_client.post(
        "/api/v1/system/audit-theater/record-access",
        json={
            "session_id": session_id,
            "resource_id": "/src/confidential.env",
            "kind": "file",
            "mode": "read",
            "scope_detail": "lines 1-30",
            "size_bytes": 1024,
            "line_count": 30,
            "success": True,
        },
    )
    assert r1.status_code == 200
    assert r1.json()["status"] == "recorded"

    r2 = await async_client.post(
        "/api/v1/system/audit-theater/record-access",
        json={
            "session_id": session_id,
            "resource_id": "memory://user_private_notes",
            "kind": "memory",
            "mode": "read",
            "scope_detail": "top_k=5",
            "success": True,
        },
    )
    assert r2.status_code == 200

    r3 = await async_client.post(
        "/api/v1/system/audit-theater/record-access",
        json={
            "session_id": session_id,
            "resource_id": "mcp://notion/read_database",
            "kind": "connector_mcp",
            "mode": "execute",
            "scope_detail": "method=read_database",
            "success": True,
        },
    )
    assert r3.status_code == 200

    r4 = await async_client.post(
        "/api/v1/system/audit-theater/record-access",
        json={
            "session_id": session_id,
            "resource_id": "https://api.slack.com/conversations",
            "kind": "web_network",
            "mode": "read",
            "scope_detail": "GET /conversations",
            "success": True,
        },
    )
    assert r4.status_code == 200

    # 3. Record timeline events (Plan declaration + Executed action)
    ev1 = await async_client.post(
        "/api/v1/system/audit-theater/record-event",
        json={
            "session_id": session_id,
            "step_name": "Planned Intention: Inspect user notes",
            "tool_name": "recall_memory",
            "is_plan": True,
            "status": "in_progress",
            "inputs_summary": "Querying notes for session context",
        },
    )
    assert ev1.status_code == 200

    ev2 = await async_client.post(
        "/api/v1/system/audit-theater/record-event",
        json={
            "session_id": session_id,
            "step_name": "Executed Action: Read confidential file",
            "tool_name": "view_file",
            "is_plan": False,
            "status": "completed",
            "duration_ms": 55,
            "inputs_summary": "/src/confidential.env",
        },
    )
    assert ev2.status_code == 200

    # 4. Fetch full session ledger
    ledger_resp = await async_client.get(f"/api/v1/system/audit-theater/ledger/{session_id}")
    assert ledger_resp.status_code == 200
    ledger = ledger_resp.json()

    assert ledger["session_id"] == session_id
    assert ledger["total_resources_accessed"] == 4
    assert ledger["total_files_read"] == 1
    assert ledger["total_memories_queried"] == 1
    assert ledger["total_network_domains_visited"] == 1
    assert ledger["lie_immune_verified"] is True
    assert len(ledger["digest_sha256"]) == 64
    assert len(ledger["events"]) == 2
    assert len(ledger["resources"]) == 4
