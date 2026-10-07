"""
[POS] tests/api/memory/test_memory_mcp_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.memory.mcp_router
[OUTPUT] test_get_mcp_info_api, test_remember_and_query_mcp_api, test_remember_with_secret_redaction_mcp_api, test_finalize_and_get_handoff_mcp_api

Unit test suite for memory MCP server interop and ai-memory wire parity API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from myrm_agent_harness.toolkits.memory.handoff import AgentHandoffEngine
from myrm_agent_harness.toolkits.memory.privacy_gate import (
    MemoryPrivacyBoundaryGate,
    MemoryPrivacyConfig,
)
from starlette.testclient import TestClient

from app.api.memory.mcp_router import router as memory_mcp_router
from app.services.memory.memory_mcp_service import (
    MemoryMcpService,
    get_memory_mcp_service,
)


@pytest.fixture
def mcp_test_client() -> Generator[TestClient, None, None]:
    """Provide isolated TestClient mounting memory MCP router."""
    with tempfile.TemporaryDirectory() as td:
        temp_path = Path(td)
        engine = AgentHandoffEngine(storage_dir=temp_path / "handoffs")
        gate = MemoryPrivacyBoundaryGate(
            config=MemoryPrivacyConfig(
                block_on_critical=False,
                strict_mode=False,
            )
        )
        service = MemoryMcpService(
            handoff_engine=engine,
            privacy_gate=gate,
            server_name="test-mcp-server",
        )

        test_app = FastAPI()
        test_app.include_router(memory_mcp_router, prefix="/api/memory")
        test_app.dependency_overrides[get_memory_mcp_service] = lambda: service

        with TestClient(test_app) as client:
            yield client


def test_get_mcp_info_api(mcp_test_client: TestClient) -> None:
    """Verify metadata and registered tool list of the memory MCP server."""
    resp = mcp_test_client.get("/api/memory/mcp/info")
    assert resp.status_code == 200
    data = resp.json()

    assert data["server_name"] == "test-mcp-server"
    assert data["version"] == "1.0.0"
    assert "ai-memory-v1" in data["compatible_with"]
    assert "claude-code" in data["compatible_with"]
    assert "query_memory" in data["tools_exposed"]
    assert "get_handoff" in data["tools_exposed"]
    assert "finalize_session" in data["tools_exposed"]
    assert "remember" in data["tools_exposed"]


def test_remember_and_query_mcp_api(mcp_test_client: TestClient) -> None:
    """Verify storing facts and searching memories via ai-memory wire signatures."""
    # 1. Query initially empty
    resp_empty = mcp_test_client.post(
        "/api/memory/mcp/query",
        json={"query": "microservices", "limit": 5},
    )
    assert resp_empty.status_code == 200
    assert "No matching memories found" in resp_empty.json()["content_markdown"]

    # 2. Remember new fact
    resp_rem = mcp_test_client.post(
        "/api/memory/mcp/remember",
        json={
            "topic": "Architecture",
            "note": "We adopt microservices pattern for decoupled deployment",
        },
    )
    assert resp_rem.status_code == 200
    rem_data = resp_rem.json()
    assert rem_data["status"] == "stored"
    assert "Stored fact under topic [Architecture]" in rem_data["message"]

    # 3. Query matching memory
    resp_search = mcp_test_client.post(
        "/api/memory/mcp/query",
        json={"query": "microservices", "limit": 5},
    )
    assert resp_search.status_code == 200
    search_data = resp_search.json()
    assert search_data["count"] == 1
    assert "[Architecture]" in search_data["content_markdown"]
    assert "microservices pattern" in search_data["content_markdown"]


def test_remember_with_secret_redaction_mcp_api(mcp_test_client: TestClient) -> None:
    """Verify sensitive tokens are scrubbed when ingested via MCP remember endpoint."""
    resp_rem = mcp_test_client.post(
        "/api/memory/mcp/remember",
        json={
            "topic": "SecurityKeys",
            "note": "Found active auth token sk-proj-1234567890abcdef1234567890abcdef for testing",
        },
    )
    assert resp_rem.status_code == 200
    data = resp_rem.json()
    assert data["status"] == "sanitized_and_stored"

    # Verify query returns sanitized token
    resp_q = mcp_test_client.post(
        "/api/memory/mcp/query",
        json={"query": "SecurityKeys", "limit": 5},
    )
    assert resp_q.status_code == 200
    q_data = resp_q.json()
    assert "[REDACTED:API_KEY]" in q_data["content_markdown"]
    assert "sk-proj-1234567890abcdef1234567890abcdef" not in q_data["content_markdown"]


def test_finalize_and_get_handoff_mcp_api(mcp_test_client: TestClient) -> None:
    """Verify session finalization and subsequent retrieval of handoff memorandum."""
    # 1. Retrieve initially empty handoff
    resp_init = mcp_test_client.get("/api/memory/mcp/handoff")
    assert resp_init.status_code == 200
    assert "No pending handoff memorandum found" in resp_init.text

    # 2. Finalize working session
    summary = "Completed MCP wire adapter implementation and FastAPI routes"
    next_actions = ["Write unit tests", "Run architecture gates"]
    failed = ["Exposing unredacted raw SQLite store"]

    resp_fin = mcp_test_client.post(
        "/api/memory/mcp/finalize",
        json={
            "summary": summary,
            "next_steps": next_actions,
            "failed_approaches": failed,
            "session_id": "test-session-mcp-api",
        },
    )
    assert resp_fin.status_code == 200
    fin_data = resp_fin.json()
    assert fin_data["status"] == "recorded"
    assert "Session finalized successfully" in fin_data["message"]

    # 3. Retrieve pending handoff markdown
    resp_handoff = mcp_test_client.get("/api/memory/mcp/handoff")
    assert resp_handoff.status_code == 200
    handoff_md = resp_handoff.text
    assert "Active Handoff Memorandum" in handoff_md
    assert summary in handoff_md
    assert "1. Write unit tests" in handoff_md
    assert "2. Run architecture gates" in handoff_md
    assert "Exposing unredacted raw SQLite store" in handoff_md
