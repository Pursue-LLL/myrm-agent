"""Integration tests for Sandbox Container Device Whitelist REST endpoints.

[POS] tests/api/security/test_device_whitelist_endpoints.py
[INPUT] app.api.security.device_whitelist_router, app.services.security.device_whitelist_service
[OUTPUT] End-to-end integration tests for device inspection, batch sanitization with block device stripping,
cgroup rules generation, and policy updates.
Strict typing applied: No `Any` types allowed. Enforced under 400 lines limit.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.device_whitelist_router import (
    device_whitelist_router,
    get_device_service,
)
from app.services.security.device_whitelist_service import (
    ContainerDeviceWhitelistService,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = ContainerDeviceWhitelistService()
    app = FastAPI()
    app.include_router(device_whitelist_router, prefix="/api/security")
    app.dependency_overrides[get_device_service] = lambda: service
    return TestClient(app)


def test_endpoint_inspect_device(client: TestClient) -> None:
    # 1. Standard pseudo device -> ALLOW
    resp_null = client.post("/api/security/device-whitelist/inspect", json={"device_path": "/dev/null"})
    assert resp_null.status_code == 200
    data_null = resp_null.json()
    assert data_null["action"] == "ALLOW"
    assert data_null["matched_rule"] == "ALLOWED_VIRTUAL_DEVICE"
    assert data_null["device_type"] == "c"

    # 2. Block device -> STRIP
    resp_sda = client.post("/api/security/device-whitelist/inspect", json={"device_path": "/dev/sda1"})
    assert resp_sda.status_code == 200
    data_sda = resp_sda.json()
    assert data_sda["action"] == "STRIP"
    assert data_sda["matched_rule"] == "STRIPPED_PHYSICAL_BLOCK_DEVICE"
    assert data_sda["device_type"] == "b"

    # 3. Host hardware device -> STRIP
    resp_mem = client.post("/api/security/device-whitelist/inspect", json={"device_path": "/dev/mem"})
    assert resp_mem.status_code == 200
    data_mem = resp_mem.json()
    assert data_mem["action"] == "STRIP"
    assert data_mem["matched_rule"] == "STRIPPED_HOST_HARDWARE_DEVICE"


def test_endpoint_sanitize_device_list(client: TestClient) -> None:
    req_payload = {
        "devices": [
            "/dev/null",
            "/dev/urandom",
            "/dev/sda",
            "/dev/nvme0n1",
            "/dev/kmsg",
        ]
    }
    resp = client.post("/api/security/device-whitelist/sanitize", json=req_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_inspected"] == 5
    assert data["is_fully_compliant"] is False
    assert set(data["allowed_devices"]) == {"/dev/null", "/dev/urandom"}
    assert set(data["stripped_devices"]) == {"/dev/sda", "/dev/nvme0n1", "/dev/kmsg"}
    assert len(data["reasons"]) == 3


def test_endpoint_cgroup_rules_and_standard_devices(client: TestClient) -> None:
    # 1. Cgroup rules
    resp_cg = client.get("/api/security/device-whitelist/cgroup-rules")
    assert resp_cg.status_code == 200
    cg_data = resp_cg.json()
    assert len(cg_data["cgroup_rules"]) >= 7
    assert any("c 1:3 rwm" in r for r in cg_data["cgroup_rules"])
    assert any("--device-cgroup-rule=c 1:3 rwm" == a for a in cg_data["docker_device_args"])

    # 2. Standard devices
    resp_devs = client.get("/api/security/device-whitelist/standard-devices")
    assert resp_devs.status_code == 200
    devs_list = resp_devs.json()
    assert len(devs_list) >= 7
    paths = {d["path"] for d in devs_list}
    assert "/dev/null" in paths
    assert "/dev/tty" in paths


def test_endpoint_policy_lifecycle(client: TestClient) -> None:
    # 1. Get default policy
    resp_get = client.get("/api/security/device-whitelist/policy")
    assert resp_get.status_code == 200
    pol = resp_get.json()
    assert pol["strict_minimal_allowlist"] is True
    assert pol["strip_block_devices"] is True

    # 2. Update policy
    update_payload = {
        "strict_minimal_allowlist": True,
        "strip_block_devices": True,
        "strip_host_hardware_devices": True,
        "custom_allowed_devices": ["/dev/special_pipe"],
    }
    resp_put = client.put("/api/security/device-whitelist/policy", json=update_payload)
    assert resp_put.status_code == 200
    assert resp_put.json()["custom_allowed_devices"] == ["/dev/special_pipe"]

    # 3. Test that custom device is now accepted
    resp_insp = client.post("/api/security/device-whitelist/inspect", json={"device_path": "/dev/special_pipe"})
    assert resp_insp.status_code == 200
    assert resp_insp.json()["action"] == "ALLOW"
