"""Tests for self-hosted machine fleet management, telemetry heartbeats, and live takeover endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.machines.router import router as machines_router
from app.services.machines import MachinePlatform, MachineService


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated FastAPI client with machines router mounted."""
    MachineService.reset_instance()
    app = FastAPI(title="Machines Test App")
    app.include_router(machines_router, prefix="/api/v1")
    return TestClient(app)


def test_list_and_get_machines(client: TestClient) -> None:
    """List pre-seeded fleet nodes and get single machine node details."""
    response = client.get("/api/v1/machines")
    assert response.status_code == 200
    machines = response.json()
    assert len(machines) >= 2

    mac_node = next((m for m in machines if m["platform"] == "darwin"), None)
    assert mac_node is not None
    assert "Mac Studio" in mac_node["display_name"]
    assert mac_node["metrics"]["cpu_usage_pct"] > 0

    # Get single machine
    single_res = client.get(f"/api/v1/machines/{mac_node['machine_id']}")
    assert single_res.status_code == 200
    assert single_res.json()["machine_id"] == mac_node["machine_id"]

    # Non-existent node
    missing_res = client.get("/api/v1/machines/non-existent-node")
    assert missing_res.status_code == 404


def test_generate_registration_token_for_platforms(client: TestClient) -> None:
    """Generate registration token and copy-pasteable command for macOS and Windows."""
    # Darwin platform
    res_mac = client.post("/api/v1/machines/token?platform=darwin")
    assert res_mac.status_code == 201
    data_mac = res_mac.json()
    assert data_mac["platform"] == "darwin"
    assert "curl -fsSL https://get.myrm.ai/connect.sh" in data_mac["quick_command"]
    assert data_mac["token"].startswith("tok-")

    # Windows platform
    res_win = client.post("/api/v1/machines/token?platform=windows")
    assert res_win.status_code == 201
    data_win = res_win.json()
    assert data_win["platform"] == "windows"
    assert "powershell" in data_win["quick_command"]


def test_machine_heartbeat_reporting(client: TestClient) -> None:
    """Report live telemetry heartbeat and observe metrics update."""
    heartbeat_payload = {
        "cpu_usage_pct": 88.5,
        "memory_usage_pct": 74.2,
        "disk_usage_pct": 55.0,
        "active_tasks_count": 8,
    }

    res = client.post(
        "/api/v1/machines/mach-mac-studio-01/heartbeat",
        json=heartbeat_payload,
    )
    assert res.status_code == 200
    node = res.json()
    assert node["metrics"]["cpu_usage_pct"] == 88.5
    assert node["metrics"]["active_tasks_count"] == 8
    assert node["status"] == "busy"


def test_live_takeover_and_release_lifecycle(client: TestClient) -> None:
    """Initiate human takeover, verify state transition, and release back to agent."""
    # 1. Initiate takeover
    takeover_res = client.post(
        "/api/v1/machines/mach-mac-studio-01/takeover",
        json={"action": "takeover", "operator_id": "engineer-alice"},
    )
    assert takeover_res.status_code == 200
    session = takeover_res.json()
    assert session["state"] == "human_takeover"
    assert session["operator_id"] == "engineer-alice"

    # Verify machine status changed to takeover
    node_res = client.get("/api/v1/machines/mach-mac-studio-01")
    assert node_res.json()["status"] == "takeover"

    # 2. Get active takeover session
    active_res = client.get("/api/v1/machines/mach-mac-studio-01/takeover")
    assert active_res.status_code == 200
    assert active_res.json()["state"] == "human_takeover"

    # 3. Release takeover back to agent
    release_res = client.post("/api/v1/machines/mach-mac-studio-01/release")
    assert release_res.status_code == 200
    released_session = release_res.json()
    assert released_session["state"] == "agent"
    assert released_session["operator_id"] is None

    # Verify machine status returned to online
    node_res_after = client.get("/api/v1/machines/mach-mac-studio-01")
    assert node_res_after.json()["status"] == "online"
