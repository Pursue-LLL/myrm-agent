"""
[POS] tests/api/agents/test_device_mesh_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, app.api.agents.device_mesh_router, myrm_agent_harness.agent.sub_agents.device_mesh
[OUTPUT] test_register_and_get_mesh_node_api, test_pair_mesh_node_api, test_heartbeat_and_list_filtering_api, test_dispatch_command_api, test_delete_mesh_node_api

FastAPI integration test suite for edge device mesh scheduling, node pairing, heartbeats, and command dispatch.
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.device_mesh.scheduler import (
    EdgeDeviceMeshScheduler,
)
from starlette.testclient import TestClient

from app.api.agents.device_mesh_router import router as device_mesh_router
from app.services.agent.device_mesh_service import (
    DeviceMeshService,
    get_device_mesh_service,
)


@pytest.fixture
def mesh_client() -> Generator[TestClient, None, None]:
    """Provide isolated TestClient fixture mounting device mesh router."""
    scheduler = EdgeDeviceMeshScheduler(stale_timeout_seconds=30.0)
    service = DeviceMeshService(scheduler=scheduler)

    test_app = FastAPI()
    test_app.include_router(device_mesh_router, prefix="/api/agents")
    test_app.dependency_overrides[get_device_mesh_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_register_and_get_mesh_node_api(mesh_client: TestClient) -> None:
    """Verify edge device node registration and direct lookup."""
    reg_payload = {
        "node_id": "rpi-living-room",
        "name": "Living Room Raspberry Pi 5",
        "kind": "raspberry_pi",
        "ip_or_hostname": "192.168.1.105",
        "capabilities": ["camera", "gpio", "sensor_reading"],
        "pairing_token": "secret-rpi-token",
        "auto_pair": True,
    }
    resp = mesh_client.post("/api/agents/device-mesh/nodes", json=reg_payload)
    assert resp.status_code == 201
    created_node = resp.json()
    assert created_node["node_id"] == "rpi-living-room"
    assert created_node["name"] == "Living Room Raspberry Pi 5"
    assert created_node["kind"] == "raspberry_pi"
    assert created_node["status"] == "online"
    assert "gpio" in created_node["capabilities"]
    assert created_node["ip_or_hostname"] == "192.168.1.105"

    # Verify GET lookup
    get_resp = mesh_client.get("/api/agents/device-mesh/nodes/rpi-living-room")
    assert get_resp.status_code == 200
    fetched_node = get_resp.json()
    assert fetched_node["node_id"] == "rpi-living-room"
    assert fetched_node["ip_or_hostname"] == "192.168.1.105"

    # Verify not found lookup
    not_found_resp = mesh_client.get("/api/agents/device-mesh/nodes/non-existent-device")
    assert not_found_resp.status_code == 404


def test_pair_mesh_node_api(mesh_client: TestClient) -> None:
    """Verify handshake authentication for unpaired edge nodes."""
    reg_payload = {
        "node_id": "mac-studio-m2",
        "name": "Local Mac Studio Node",
        "kind": "mac_mini",
        "ip_or_hostname": "192.168.1.88",
        "capabilities": ["metal_acceleration", "subagent_host"],
        "pairing_token": "m2-ultra-secret",
        "auto_pair": False,
    }
    reg_resp = mesh_client.post("/api/agents/device-mesh/nodes", json=reg_payload)
    assert reg_resp.status_code == 201
    assert reg_resp.json()["status"] == "unpaired"

    # Pairing with invalid token
    bad_pair_resp = mesh_client.post(
        "/api/agents/device-mesh/nodes/mac-studio-m2/pair",
        json={"pairing_token": "wrong-token"},
    )
    assert bad_pair_resp.status_code == 400
    assert "Invalid token" in bad_pair_resp.json()["detail"]

    # Pairing with valid token
    good_pair_resp = mesh_client.post(
        "/api/agents/device-mesh/nodes/mac-studio-m2/pair",
        json={"pairing_token": "m2-ultra-secret"},
    )
    assert good_pair_resp.status_code == 200
    paired_node = good_pair_resp.json()
    assert paired_node["status"] == "online"

    # Pairing non-existent node
    missing_pair_resp = mesh_client.post(
        "/api/agents/device-mesh/nodes/missing-node/pair",
        json={"pairing_token": "test"},
    )
    assert missing_pair_resp.status_code == 400


def test_heartbeat_and_list_filtering_api(mesh_client: TestClient) -> None:
    """Verify heartbeat metrics updates and collection filtering by kind and status."""
    # Register 2 nodes: one online, one unpaired
    mesh_client.post(
        "/api/agents/device-mesh/nodes",
        json={
            "node_id": "gpu-node-01",
            "name": "RTX 4090 Workstation",
            "kind": "linux_server",
            "ip_or_hostname": "192.168.1.200",
            "pairing_token": "gpu-secret-token",
            "auto_pair": True,
        },
    )
    mesh_client.post(
        "/api/agents/device-mesh/nodes",
        json={
            "node_id": "rpi-zero-01",
            "name": "Pi Zero Camera",
            "kind": "raspberry_pi",
            "ip_or_hostname": "192.168.1.201",
            "pairing_token": "rpi-tok",
            "auto_pair": False,
        },
    )

    # Send heartbeat with telemetry to gpu-node-01
    hb_payload = {
        "telemetry": {
            "cpu_usage_pct": 82.5,
            "memory_usage_pct": 65.0,
            "gpu_usage_pct": 95.0,
            "uptime_seconds": 7200.0,
            "active_tasks": 3,
        }
    }
    hb_resp = mesh_client.post(
        "/api/agents/device-mesh/nodes/gpu-node-01/heartbeat",
        json=hb_payload,
    )
    assert hb_resp.status_code == 200
    updated_node = hb_resp.json()
    assert updated_node["status"] == "online"
    assert updated_node["telemetry"]["cpu_usage_pct"] == 82.5
    assert updated_node["telemetry"]["gpu_usage_pct"] == 95.0
    assert updated_node["telemetry"]["active_tasks"] == 3

    # Filter by kind = linux_server
    filter_kind_resp = mesh_client.get(
        "/api/agents/device-mesh/nodes",
        params={"kind": "linux_server"},
    )
    assert filter_kind_resp.status_code == 200
    linux_list = filter_kind_resp.json()
    assert linux_list["total_count"] == 1
    assert linux_list["nodes"][0]["node_id"] == "gpu-node-01"

    # Filter by status = unpaired
    filter_status_resp = mesh_client.get(
        "/api/agents/device-mesh/nodes",
        params={"status": "unpaired"},
    )
    assert filter_status_resp.status_code == 200
    unpaired_list = filter_status_resp.json()
    assert unpaired_list["total_count"] == 1
    assert unpaired_list["nodes"][0]["node_id"] == "rpi-zero-01"

    # Heartbeat on missing node returns 404
    missing_hb = mesh_client.post(
        "/api/agents/device-mesh/nodes/ghost-node/heartbeat",
        json={},
    )
    assert missing_hb.status_code == 404


def test_dispatch_command_api(mesh_client: TestClient) -> None:
    """Verify dispatching execution task to registered node."""
    mesh_client.post(
        "/api/agents/device-mesh/nodes",
        json={
            "node_id": "test-box-01",
            "name": "Automated Test Box",
            "kind": "linux_server",
            "ip_or_hostname": "192.168.1.199",
            "pairing_token": "box-secret-token",
            "auto_pair": True,
        },
    )

    dispatch_payload = {
        "node_id": "test-box-01",
        "command": "uname -a",
        "timeout_seconds": 15.0,
        "environment": {"ENV": "test"},
    }
    disp_resp = mesh_client.post("/api/agents/device-mesh/dispatch", json=dispatch_payload)
    assert disp_resp.status_code == 200
    result = disp_resp.json()
    assert result["success"] is True
    assert result["node_id"] == "test-box-01"
    assert "Executed 'uname -a'" in result["stdout"]

    # Dispatch to unpaired node results in success=False
    mesh_client.post(
        "/api/agents/device-mesh/nodes",
        json={
            "node_id": "unpaired-box-02",
            "name": "Unpaired Test Box",
            "kind": "linux_server",
            "ip_or_hostname": "192.168.1.198",
            "auto_pair": False,
        },
    )
    unpaired_disp = mesh_client.post(
        "/api/agents/device-mesh/dispatch",
        json={"node_id": "unpaired-box-02", "command": "echo test"},
    )
    assert unpaired_disp.status_code == 200
    assert unpaired_disp.json()["success"] is False
    assert "is unpaired" in unpaired_disp.json()["stderr"]

    # Dispatch to non-existent node
    bad_disp = mesh_client.post(
        "/api/agents/device-mesh/dispatch",
        json={"node_id": "unknown-node", "command": "echo test"},
    )
    assert bad_disp.status_code == 404


def test_delete_mesh_node_api(mesh_client: TestClient) -> None:
    """Verify node deregistration and deletion lifecycle."""
    mesh_client.post(
        "/api/agents/device-mesh/nodes",
        json={
            "node_id": "node-to-delete",
            "name": "Decommissioned Device",
            "kind": "custom",
            "ip_or_hostname": "192.168.1.50",
            "auto_pair": True,
        },
    )
    # Deletion
    del_resp = mesh_client.delete("/api/agents/device-mesh/nodes/node-to-delete")
    assert del_resp.status_code == 204

    # Subsequent GET returns 404
    get_resp = mesh_client.get("/api/agents/device-mesh/nodes/node-to-delete")
    assert get_resp.status_code == 404
