"""Unit tests for Heterogeneous External Agent Bridge & CLI Adapter API endpoints.

[INPUT]
- app.api.agents.external_agent_bridge_router.router
- app.services.agent.external_agent_bridge_service.ExternalAgentBridgeService

[OUTPUT]
- Pytest test cases verifying external agent registration, probe, execution, and verifiable receipt history.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_external_agent_bridge_api.py
"""

from __future__ import annotations

import sys
from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.external_agent_bridge_router import (
    get_external_agent_bridge_service,
)
from app.api.agents.external_agent_bridge_router import (
    router as external_agent_bridge_router,
)
from app.services.agent.external_agent_bridge_service import (
    ExternalAgentBridgeService,
)


@pytest.fixture
def mock_bridge_service() -> ExternalAgentBridgeService:
    return ExternalAgentBridgeService()


@pytest.fixture
def bridge_client(
    mock_bridge_service: ExternalAgentBridgeService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(external_agent_bridge_router)
    app.dependency_overrides[get_external_agent_bridge_service] = lambda: mock_bridge_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_external_agent_crud_and_listing(bridge_client: TestClient) -> None:
    # 1. Register agent
    register_payload = {
        "agent_id": "claude-code-worker",
        "name": "Claude Code CLI Lane",
        "kind": "claude-code",
        "command": "claude",
        "args": ["--non-interactive"],
        "timeout_seconds": 30.0,
    }
    resp = bridge_client.post("/agents/external-bridge/agents", json=register_payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["agent_id"] == "claude-code-worker"

    # 2. List agents
    list_resp = bridge_client.get("/agents/external-bridge/agents")
    assert list_resp.status_code == 200
    list_body = list_resp.json()
    assert list_body["data"]["total"] == 1
    assert list_body["data"]["agents"][0]["agent_id"] == "claude-code-worker"

    # 3. Get agent
    get_resp = bridge_client.get("/agents/external-bridge/agents/claude-code-worker")
    assert get_resp.status_code == 200
    assert get_resp.json()["data"]["name"] == "Claude Code CLI Lane"

    # 4. Unregister agent
    del_resp = bridge_client.delete("/agents/external-bridge/agents/claude-code-worker")
    assert del_resp.status_code == 200
    assert del_resp.json()["data"]["action"] == "unregistered"

    # 5. Get after unregister returns 404
    get_404 = bridge_client.get("/agents/external-bridge/agents/claude-code-worker")
    assert get_404.status_code == 404


def test_external_agent_probe_endpoint(bridge_client: TestClient) -> None:
    # Register python executable as generic CLI
    register_payload = {
        "agent_id": "py-stdio-lane",
        "name": "Python Stdio Runner",
        "kind": "generic-stdio",
        "command": sys.executable,
        "timeout_seconds": 10.0,
    }
    bridge_client.post("/agents/external-bridge/agents", json=register_payload)

    # Probe valid executable
    probe_resp = bridge_client.get("/agents/external-bridge/agents/py-stdio-lane/probe")
    assert probe_resp.status_code == 200
    data = probe_resp.json()["data"]
    assert data["agent_id"] == "py-stdio-lane"
    assert data["is_healthy"] is True

    # Probe non-existent agent returns 404
    resp_404 = bridge_client.get("/agents/external-bridge/agents/non-existent-agent/probe")
    assert resp_404.status_code == 404


def test_external_agent_execute_and_receipts(bridge_client: TestClient) -> None:
    # Register python echo worker
    register_payload = {
        "agent_id": "echo-lane",
        "name": "Echo CLI Lane",
        "kind": "generic-stdio",
        "command": sys.executable,
        "args": ["-c", "import sys; print('OUTPUT:' + sys.stdin.read().upper())"],
        "timeout_seconds": 5.0,
    }
    bridge_client.post("/agents/external-bridge/agents", json=register_payload)

    # Execute task
    exec_payload = {
        "execution_id": "exec-lane-101",
        "input_text": "run hermes task",
    }
    exec_resp = bridge_client.post("/agents/external-bridge/agents/echo-lane/execute", json=exec_payload)
    assert exec_resp.status_code == 200
    receipt = exec_resp.json()["data"]

    assert receipt["execution_id"] == "exec-lane-101"
    assert receipt["status"] == "completed"
    assert receipt["exit_code"] == 0
    assert "OUTPUT:RUN HERMES TASK" in receipt["stdout_summary"]
    assert len(receipt["receipt_hash"]) == 64

    # Fetch receipts history
    hist_resp = bridge_client.get("/agents/external-bridge/agents/echo-lane/receipts")
    assert hist_resp.status_code == 200
    hist = hist_resp.json()["data"]
    assert hist["total"] == 1
    assert hist["receipts"][0]["execution_id"] == "exec-lane-101"
