"""API integration tests for the Lightweight P2P Agent Socket Mesh Protocol (Item 73).

[INPUT]
- app.api.agents.socket_mesh_router.router
- app.services.agent.socket_mesh_service.get_socket_mesh_service

[OUTPUT]
- Pytest assertions verifying zero-broker peer registration, atomic prompt/reply envelope
  dispatch, in-flight await futures, peer health ping-pong, audit trail, and stale cleanup.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_socket_mesh_api.py
"""

from __future__ import annotations

import tempfile
from typing import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.socket_mesh_router import router as socket_mesh_router
from app.services.agent.socket_mesh_service import SocketMeshService


@pytest.fixture
def tmp_mesh_dir() -> Generator[str, None, None]:
    """Provide isolated temporary directory for socket mesh tests."""
    with tempfile.TemporaryDirectory() as d:
        yield d


@pytest.fixture
def client(tmp_mesh_dir: str) -> Generator[TestClient, None, None]:
    """TestClient fixture with isolated SocketMeshService and router attached."""
    SocketMeshService.reset_instance()
    # Initialize singleton pointing to temporary test directory
    SocketMeshService.get_instance(base_dir=tmp_mesh_dir)

    app = FastAPI()
    app.include_router(socket_mesh_router)
    with TestClient(app) as test_client:
        yield test_client

    SocketMeshService.reset_instance()


def test_register_and_list_peers_api(client: TestClient) -> None:
    """Test registering agent peers and querying peer list."""
    proj = "proj-mesh-test"

    # Register first peer
    resp1 = client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={
            "name": "orchestrator",
            "purpose": "DAG Master",
            "model": "gpt-5",
            "pid": 1111,
            "context_used_pct": 15.5,
            "queue_depth": 1,
        },
    )
    assert resp1.status_code == 201
    data1 = resp1.json()
    assert data1["name"] == "orchestrator"
    assert data1["purpose"] == "DAG Master"
    assert data1["status"] == "online"

    # Register second peer
    resp2 = client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={
            "name": "analyst",
            "purpose": "Log Analysis",
            "model": "claude-3-7-sonnet",
            "pid": 2222,
            "context_used_pct": 28.0,
            "queue_depth": 0,
        },
    )
    assert resp2.status_code == 201
    assert resp2.json()["name"] == "analyst"

    # List peers
    resp_list = client.get(f"/agents/socket-mesh/projects/{proj}/peers")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["total_peers"] == 2
    names = {p["name"] for p in list_data["peers"]}
    assert "orchestrator" in names
    assert "analyst" in names

    # Single peer query
    resp_single = client.get(f"/agents/socket-mesh/projects/{proj}/peers/orchestrator")
    assert resp_single.status_code == 200
    assert resp_single.json()["name"] == "orchestrator"


def test_peer_not_found_404(client: TestClient) -> None:
    """Test querying nonexistent peer returns 404."""
    resp = client.get("/agents/socket-mesh/projects/dummy/peers/ghost")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_peer_send_reply_and_await_api(client: TestClient) -> None:
    """Test full cycle of prompt dispatch, peer reply, and await fulfillment."""
    proj = "proj-comm-test"

    # Register sender and receiver
    client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={"name": "sender_bot", "purpose": "Requester"},
    )
    client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={"name": "worker_bot", "purpose": "Executor"},
    )

    # 1. Sender dispatches prompt
    send_resp = client.post(
        f"/agents/socket-mesh/projects/{proj}/messages/send",
        json={
            "sender_name": "sender_bot",
            "target_name": "worker_bot",
            "prompt": "Evaluate cryptographic security bounds",
            "timeout_seconds": 10.0,
        },
    )
    assert send_resp.status_code == 200
    send_data = send_resp.json()
    assert send_data["success"] is True
    msg_id = send_data["msg_id"]
    assert bool(msg_id) is True

    # 2. Worker replies
    reply_resp = client.post(
        f"/agents/socket-mesh/projects/{proj}/messages/reply",
        json={
            "responder_name": "worker_bot",
            "msg_id": msg_id,
            "response_text": "Security level 256-bit AES consensus verified.",
        },
    )
    assert reply_resp.status_code == 200
    assert reply_resp.json()["success"] is True

    # 3. Sender awaits response
    await_resp = client.get(
        f"/agents/socket-mesh/projects/{proj}/messages/{msg_id}/await?sender_name=sender_bot&timeout_seconds=5.0",
    )
    assert await_resp.status_code == 200
    await_data = await_resp.json()
    assert await_data["success"] is True
    assert "256-bit AES consensus verified" in str(await_data["response"])


def test_peer_ping_api(client: TestClient) -> None:
    """Test health probe pinging of a peer."""
    proj = "proj-ping-test"

    client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={"name": "ping_source", "purpose": "Sentinel"},
    )
    client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={"name": "target_receiver", "purpose": "Search Agent"},
    )

    ping_resp = client.post(
        f"/agents/socket-mesh/projects/{proj}/peers/target_receiver/ping?sender_name=ping_source&timeout_seconds=5.0",
    )
    assert ping_resp.status_code == 200
    ping_data = ping_resp.json()
    assert ping_data["success"] is True
    assert "PONG from target_receiver" in str(ping_data["response"])
    assert "Search Agent" in str(ping_data["response"])


def test_audit_logs_and_cleanup_api(client: TestClient) -> None:
    """Test retrieving audit logs and cleaning up stale peers."""
    proj = "proj-audit-test"

    # Register and unregister peer
    client.post(
        f"/agents/socket-mesh/projects/{proj}/peers",
        json={"name": "ephemeral_bot", "purpose": "Temporary Node"},
    )

    # Check audit logs
    log_resp = client.get(f"/agents/socket-mesh/projects/{proj}/audit-logs")
    assert log_resp.status_code == 200
    logs = log_resp.json()["logs"]
    assert len(logs) >= 1
    assert any(log["event_type"] == "NODE_STARTED" for log in logs)

    # Unregister
    del_resp = client.delete(f"/agents/socket-mesh/projects/{proj}/peers/ephemeral_bot")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    # Cleanup stale
    clean_resp = client.post(f"/agents/socket-mesh/projects/{proj}/cleanup?max_age_seconds=1.0")
    assert clean_resp.status_code == 200
    assert "cleaned_count" in clean_resp.json()
