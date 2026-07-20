"""Integration: external_cli persist gate via Agent CRUD API (real gate, no mocks)."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.integration.test_computer_use_deploy_integration import (
    local_deploy,
    sandbox_no_visual_desktop,
)


@pytest.mark.integration
def test_create_agent_rejects_external_cli_in_sandbox(
    client: TestClient,
    sandbox_no_visual_desktop: None,
) -> None:
    """Sandbox deploy must reject persisting external_cli (deploy gate)."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"ExtCLI Sandbox Gate {suffix}",
        "description": "integration",
        "system_prompt": "test",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "external_cli"],
    }
    resp = client.post("/api/agents", json=payload)
    assert resp.status_code == 400
    body = resp.json()
    message = body.get("message") or (body.get("detail") or {}).get("message", "")
    assert "not supported" in str(message).lower()


@pytest.mark.integration
def test_update_agent_rejects_external_cli_in_sandbox(
    client: TestClient,
    sandbox_no_visual_desktop: None,
) -> None:
    """Sandbox deploy must reject updating enabled_builtin_tools to include external_cli."""
    suffix = uuid.uuid4().hex[:8]
    create_payload = {
        "name": f"ExtCLI Sandbox Update {suffix}",
        "description": "integration",
        "system_prompt": "test",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "memory"],
    }
    created = client.post("/api/agents", json=create_payload)
    assert created.status_code == 200
    agent_id = created.json()["data"]["id"]

    try:
        update = client.put(
            f"/api/agents/{agent_id}",
            json={"enabled_builtin_tools": ["web_search", "memory", "external_cli"]},
        )
        assert update.status_code == 400
        update_message = update.json().get("message") or (update.json().get("detail") or {}).get("message", "")
        assert "not supported" in str(update_message).lower()
    finally:
        client.delete(f"/api/agents/{agent_id}")


@pytest.mark.integration
def test_create_agent_allows_external_cli_in_local_when_backend_exists(
    client: TestClient,
    local_deploy: None,
) -> None:
    """Local deploy + resolvable CLI backend must allow external_cli persist."""
    from app.services.agent.external_cli_gate import external_cli_backend_available
    import asyncio

    if not asyncio.run(external_cli_backend_available()):
        pytest.skip("No CLI backend on this host — success path covered by unit tests")

    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"ExtCLI Local OK {suffix}",
        "description": "integration",
        "system_prompt": "test",
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["external_cli"],
    }
    resp = client.post("/api/agents", json=payload)
    assert resp.status_code == 200
    agent_id = resp.json()["data"]["id"]
    try:
        assert "external_cli" in resp.json()["data"]["enabled_builtin_tools"]
    finally:
        client.delete(f"/api/agents/{agent_id}")
