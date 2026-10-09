"""[POS]: tests/api/memory/test_tool_backup_api.py
[INPUT]: FastAPI TestClient, isolated ToolUseBackupService, and tool backup endpoints.
[OUTPUT]: Pytest integration tests verifying record, query, retrieve by ID, stats, and purge.
"""

from collections.abc import AsyncGenerator

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from myrm_agent_harness.toolkits.memory import (
    ToolUseBackupService,
)

from app.api.memory.tool_backup import (
    get_tool_backup_service,
)
from app.api.memory.tool_backup import (
    router as tool_backup_router,
)


@pytest.fixture
def isolated_service() -> ToolUseBackupService:
    """Create isolated ToolUseBackupService backed by in-memory SQLite database."""
    return ToolUseBackupService(db_path=":memory:")


@pytest.fixture
def test_app(isolated_service: ToolUseBackupService) -> FastAPI:
    """Create FastAPI test application with injected isolated ToolUseBackupService."""
    api_app = FastAPI()
    api_app.include_router(tool_backup_router, prefix="/api/memory")
    api_app.dependency_overrides[get_tool_backup_service] = lambda: isolated_service
    return api_app


@pytest.fixture
async def client(test_app: FastAPI) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP client fixture bound to the isolated test app."""
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_tool_backup_record_and_retrieve_flow(client: AsyncClient) -> None:
    """Verify recording tool use observation and retrieving it by ID."""
    # 1. Record tool execution
    record_resp = await client.post(
        "/api/memory/tool-backup/record",
        json={
            "session_id": "sess_api_001",
            "tool_name": "bash_command",
            "raw_input": "ls -la /var/log",
            "raw_output": "syslog auth.log daemon.log",
            "tool_call_id": "call_123",
            "status": "success",
            "duration_ms": 15.4,
            "metadata": {"user": "admin"},
        },
    )
    assert record_resp.status_code == 200
    rec_data = record_resp.json()
    record_id = rec_data["id"]
    assert rec_data["session_id"] == "sess_api_001"
    assert rec_data["tool_name"] == "bash_command"
    assert rec_data["is_truncated"] is False

    # 2. Retrieve exact observation by ID
    get_resp = await client.get(f"/api/memory/tool-backup/{record_id}")
    assert get_resp.status_code == 200
    get_data = get_resp.json()
    assert get_data["id"] == record_id
    assert get_data["raw_input"] == "ls -la /var/log"
    assert get_data["raw_output"] == "syslog auth.log daemon.log"
    assert get_data["metadata"]["user"] == "admin"


@pytest.mark.asyncio
async def test_tool_backup_query_stats_and_purge_flow(client: AsyncClient) -> None:
    """Verify querying tool uses with filters, inspecting audit statistics, and purging."""
    # 1. Seed two records for sess_A and one for sess_B
    await client.post(
        "/api/memory/tool-backup/record",
        json={
            "session_id": "sess_A",
            "tool_name": "file_write",
            "raw_input": "write data",
            "raw_output": "written 10 bytes",
            "status": "success",
            "duration_ms": 10.0,
        },
    )
    await client.post(
        "/api/memory/tool-backup/record",
        json={
            "session_id": "sess_A",
            "tool_name": "file_read",
            "raw_input": "read data",
            "raw_output": "not found",
            "status": "error",
            "duration_ms": 20.0,
        },
    )
    await client.post(
        "/api/memory/tool-backup/record",
        json={
            "session_id": "sess_B",
            "tool_name": "web_search",
            "raw_input": "search topic",
            "raw_output": "found 3 hits",
            "status": "success",
            "duration_ms": 50.0,
        },
    )

    # 2. Query filtered by session_id
    query_resp = await client.post(
        "/api/memory/tool-backup/query",
        json={"session_id": "sess_A", "limit": 10, "offset": 0},
    )
    assert query_resp.status_code == 200
    query_data = query_resp.json()
    assert query_data["total"] == 2
    assert all(it["session_id"] == "sess_A" for it in query_data["items"])

    # 3. Check stats
    stats_resp = await client.get("/api/memory/tool-backup/stats")
    assert stats_resp.status_code == 200
    stats_data = stats_resp.json()
    assert stats_data["total_tool_uses"] == 3
    assert stats_data["success_count"] == 2
    assert stats_data["error_count"] == 1

    # 4. Check session-specific stats
    sess_a_stats = await client.get("/api/memory/tool-backup/stats?session_id=sess_A")
    assert sess_a_stats.status_code == 200
    assert sess_a_stats.json()["total_tool_uses"] == 2

    # 5. Purge session A
    purge_resp = await client.delete("/api/memory/tool-backup/session/sess_A")
    assert purge_resp.status_code == 200
    assert purge_resp.json()["deleted_count"] == 2

    # 6. Verify total decreased to 1
    after_stats = await client.get("/api/memory/tool-backup/stats")
    assert after_stats.json()["total_tool_uses"] == 1
