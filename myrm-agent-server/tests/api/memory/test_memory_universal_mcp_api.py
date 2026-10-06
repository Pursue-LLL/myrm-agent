"""
[POS] tests/api/memory/test_memory_universal_mcp_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, json, app.api.memory.universal_mcp_router, app.services.memory.memory_universal_mcp_service
[OUTPUT] test_generate_claude_code_and_cursor_config_api, test_generate_all_clients_config_api, test_list_supported_clients_api, test_list_exposed_mcp_tools_api

Unit test suite for Universal MCP Memory Bridge and External Client Configuration Generator API endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.memory.universal_mcp_router import (
    router as memory_universal_mcp_router,
)
from app.services.memory.memory_universal_mcp_service import (
    MemoryUniversalMcpService,
    get_memory_universal_mcp_service,
)


@pytest.fixture
def universal_mcp_test_client() -> Generator[tuple[TestClient, MemoryUniversalMcpService], None, None]:
    """Provide isolated TestClient mounting universal MCP router with clean service instance."""
    service = MemoryUniversalMcpService()

    test_app = FastAPI()
    test_app.include_router(memory_universal_mcp_router, prefix="/api/memory")
    test_app.dependency_overrides[get_memory_universal_mcp_service] = lambda: service

    with TestClient(test_app) as client:
        yield client, service


def test_generate_claude_code_and_cursor_config_api(
    universal_mcp_test_client: tuple[TestClient, MemoryUniversalMcpService],
) -> None:
    """Verify POST /api/memory/universal-mcp/config generates valid snippets for Claude Code and Cursor."""
    client, _ = universal_mcp_test_client

    # 1. Claude Code
    res_claude = client.post(
        "/api/memory/universal-mcp/config",
        json={"client_kind": "claude_code", "user_id": "alice_shared", "transport": "stdio"},
    )
    assert res_claude.status_code == 200
    claude_data = res_claude.json()
    assert claude_data["total"] == 1
    snippet = claude_data["snippets"][0]
    assert snippet["client_kind"] == "claude_code"
    assert snippet["config_format"] == "json"
    assert ".claude.json" in snippet["target_config_file_path"]

    payload = json.loads(snippet["raw_content"])
    assert "mcpServers" in payload
    assert "myrm-memory" in payload["mcpServers"]
    assert "alice_shared" in payload["mcpServers"]["myrm-memory"]["args"]

    # 2. Cursor
    res_cursor = client.post(
        "/api/memory/universal-mcp/config",
        json={"client_kind": "cursor", "user_id": "alice_shared", "transport": "stdio"},
    )
    assert res_cursor.status_code == 200
    cursor_data = res_cursor.json()
    assert cursor_data["total"] == 1
    assert cursor_data["snippets"][0]["client_kind"] == "cursor"
    assert cursor_data["snippets"][0]["target_config_file_path"] == ".cursor/mcp.json"


def test_generate_all_clients_config_api(
    universal_mcp_test_client: tuple[TestClient, MemoryUniversalMcpService],
) -> None:
    """Verify POST /api/memory/universal-mcp/config generates snippets for all supported clients when omitted."""
    client, _ = universal_mcp_test_client

    res = client.post(
        "/api/memory/universal-mcp/config",
        json={"user_id": "bob_polyglot", "transport": "stdio"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    kinds = {s["client_kind"] for s in data["snippets"]}
    assert kinds == {"claude_code", "cursor", "vscode_cline", "codebuddy", "hermes"}


def test_list_supported_clients_api(
    universal_mcp_test_client: tuple[TestClient, MemoryUniversalMcpService],
) -> None:
    """Verify GET /api/memory/universal-mcp/clients returns complete external client catalog."""
    client, _ = universal_mcp_test_client

    res = client.get("/api/memory/universal-mcp/clients")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] >= 5
    client_ids = [c["client_kind"] for c in data["clients"]]
    assert "claude_code" in client_ids
    assert "cursor" in client_ids
    assert "vscode_cline" in client_ids
    assert "codebuddy" in client_ids
    assert "hermes" in client_ids


def test_list_exposed_mcp_tools_api(
    universal_mcp_test_client: tuple[TestClient, MemoryUniversalMcpService],
) -> None:
    """Verify GET /api/memory/universal-mcp/tools introspects memory MCP tool schemas."""
    client, _ = universal_mcp_test_client

    res = client.get("/api/memory/universal-mcp/tools")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 4
    tool_names = [t["name"] for t in data["tools"]]
    assert "memory_recall" in tool_names
    assert "memory_store" in tool_names
    assert "memory_list" in tool_names
    assert "memory_manage" in tool_names
