"""API endpoint tests for Agent Blast Radius Static Inspector and Guard Attribution Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.blast_radius_inspector_router import (
    router as blast_radius_inspector_router,
)
from app.services.security.blast_radius_inspector_service import (
    BlastRadiusInspectorService,
    get_blast_radius_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = BlastRadiusInspectorService()
    app = FastAPI()
    app.include_router(blast_radius_inspector_router)
    app.dependency_overrides[get_blast_radius_service] = lambda: test_service
    return TestClient(app)


def test_inspect_profile_endpoint(client: TestClient) -> None:
    # 1. Inspect permitted profile
    resp = client.post(
        "/blast-radius/inspect-profile",
        json={
            "profile_id": "test_agent_1",
            "tools": ["write_file", "view_file"],
            "declared_file_scopes": ["/app/data"],
            "declared_api_endpoints": ["https://api.external.com/v1"],
            "declared_send_channels": ["slack_bot"],
            "installed_plugins": [],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["profile_id"] == "test_agent_1"
    assert data["pre_admission_allowed"] is True
    assert data["total_tools_count"] >= 1
    assert len(data["sinks"]) > 0

    # 2. Inspect excessive profile (rejection)
    resp_excessive = client.post(
        "/blast-radius/inspect-profile",
        json={
            "profile_id": "overprivileged_agent",
            "tools": ["bash", "run_command", "shell_exec", "write_file", "edit_file"],
            "declared_file_scopes": ["/root", "/etc", "/var"],
            "declared_api_endpoints": [f"https://ep{i}.com" for i in range(15)],
            "declared_send_channels": ["ch1", "ch2", "ch3", "ch4"],
            "installed_plugins": ["pl1", "pl2", "pl3", "pl4", "pl5"],
        },
    )
    assert resp_excessive.status_code == 200
    excessive_data = resp_excessive.json()
    assert excessive_data["pre_admission_allowed"] is False
    assert "Pre-admission rejected" in (excessive_data["admission_rejection_reason"] or "")


def test_guard_attribution_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/blast-radius/guard-attribution",
        json={
            "sinks": [
                {
                    "action_category": "WRITE_FILE",
                    "dimension": "FILES",
                    "sink_identifier": "/var/data",
                    "danger_tier": "REACHABLE_VERIFIED",
                    "description": "Local file write sink",
                }
            ],
            "active_guards": {
                "FILES": "PATH_POLICY_SANDBOX_JAIL",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["attributions"]) == 1
    assert data["attributions"][0]["guard_status"] == "GUARD_ATTRIBUTED"
    assert data["attributions"][0]["assigned_guard_name"] == "PATH_POLICY_SANDBOX_JAIL"
    assert data["remediation_required"] is False


def test_auto_repair_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/blast-radius/auto-repair",
        json={
            "sinks": [
                {
                    "action_category": "TRIGGER_API",
                    "dimension": "APIS",
                    "sink_identifier": "https://unknown-egress.com",
                    "danger_tier": "REACHABLE_VERIFIED",
                    "description": "Unguarded external HTTP egress",
                }
            ],
            "active_guards": {},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_patches"] >= 1
    patch = data["patches"][0]
    assert patch["target_sink"] == "https://unknown-egress.com"
    assert patch["injected_guard_type"] == "DOMAIN_ALLOWLIST"


def test_kill_switch_endpoints(client: TestClient) -> None:
    # 1. Engage kill switch
    trip_resp = client.post(
        "/blast-radius/kill-switch/toggle",
        json={
            "enabled": True,
            "reason": "Exfiltration alert tripped by SIEM",
            "operator": "soc_analyst",
        },
    )
    assert trip_resp.status_code == 200
    trip_data = trip_resp.json()
    assert trip_data["is_engaged"] is True
    assert trip_data["engaged_by"] == "soc_analyst"

    # 2. Check status endpoint
    status_resp = client.get("/blast-radius/kill-switch/status")
    assert status_resp.status_code == 200
    assert status_resp.json()["is_engaged"] is True

    # 3. Disengage kill switch
    reset_resp = client.post(
        "/blast-radius/kill-switch/toggle",
        json={
            "enabled": False,
            "reason": "False alarm investigated",
            "operator": "soc_admin",
        },
    )
    assert reset_resp.status_code == 200
    assert reset_resp.json()["is_engaged"] is False
