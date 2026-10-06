"""API endpoint tests for Dual-Use Skill Containment and Artifact Exfiltration Shield Suite.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import base64

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.dual_use_containment_router import (
    router as dual_use_containment_router,
)
from app.services.security.dual_use_containment_service import (
    DualUseContainmentService,
    get_dual_use_containment_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = DualUseContainmentService(allowlisted_destinations=["https://internal.vault.myrm.io"])
    app = FastAPI()
    app.include_router(dual_use_containment_router)
    app.dependency_overrides[get_dual_use_containment_service] = lambda: test_service
    return TestClient(app)


def test_evaluate_skill_ttp_endpoint(client: TestClient) -> None:
    """Test /skills/evaluate-ttp endpoint."""
    payload = {
        "skill_name": "meterpreter_session_handler",
        "description": "Establish interactive reverse shell and meterpreter C2 session.",
        "command_signatures": ["meterpreter reverse_tcp", "sessions -i 1"],
    }
    response = client.post("/dual-use-containment/skills/evaluate-ttp", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["skill_name"] == "meterpreter_session_handler"
    assert data["sensitivity_level"] == "dual_use_sensitive"
    assert data["quarantine_pod_enforced"] is True
    assert data["requires_hitl_approval"] is True
    assert "command_and_control" in data["tactics"]


def test_check_execution_gate_endpoint_host_blocked(client: TestClient) -> None:
    """Test /gate/check-execution endpoint when executed on native host."""
    payload = {
        "skill_name": "meterpreter_session_handler",
        "command_line": "run exploit/multi/handler",
        "target_host_or_ip": "10.10.10.5",
        "is_running_in_quarantine_pod": False,
        "approval_token": "",
    }
    response = client.post("/dual-use-containment/gate/check-execution", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["permitted"] is False
    assert data["enforce_quarantine_pod"] is True
    assert "strictly prohibited from running on native host" in data["reason"]


def test_check_execution_gate_endpoint_hitl_required(client: TestClient) -> None:
    """Test /gate/check-execution endpoint requiring HITL confirmation."""
    payload = {
        "skill_name": "meterpreter_session_handler",
        "command_line": "run exploit/multi/handler",
        "target_host_or_ip": "10.10.10.5",
        "is_running_in_quarantine_pod": True,
        "approval_token": "",
    }
    response = client.post("/dual-use-containment/gate/check-execution", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["permitted"] is False
    assert data["requires_hitl_modal"] is True
    assert "高危攻防指令警示" in data["hitl_prompt_warning"]


def test_evaluate_artifact_egress_endpoint_blocks_public_upload(client: TestClient) -> None:
    """Test /artifacts/evaluate-egress endpoint blocking public GitHub artifact leak."""
    fake_img = base64.b64encode(b"PNG screenshot containing internal tokens").decode("utf-8")
    payload = {
        "artifact_id": "art_scr_leak_01",
        "artifact_name": "employee_secrets_screenshot.png",
        "content_base64": fake_img,
        "target_destination": "https://github.com/public-repo/public-issues",
    }
    response = client.post("/dual-use-containment/artifacts/evaluate-egress", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_blocked"] is True
    assert data["classification"] == "restricted_artifact"
    assert "Attempted to exfiltrate private artifact" in data["violation_reason"]


def test_flight_recorder_and_metrics_endpoints(client: TestClient) -> None:
    """Test /flight-recorder/records and /metrics endpoints."""
    # 1. Trigger an egress check to generate flight recorder log
    payload = {
        "artifact_id": "art_02",
        "artifact_name": "safe_doc.txt",
        "target_destination": "https://internal.vault.myrm.io/docs",
    }
    client.post("/dual-use-containment/artifacts/evaluate-egress", json=payload)

    # 2. Query flight recorder logs
    resp_logs = client.get("/dual-use-containment/flight-recorder/records?limit=10")
    assert resp_logs.status_code == 200
    logs = resp_logs.json()
    assert len(logs) >= 1

    # 3. Query metrics
    resp_metrics = client.get("/dual-use-containment/metrics")
    assert resp_metrics.status_code == 200
    metrics = resp_metrics.json()
    assert "total_artifact_scans" in metrics
    assert "exfiltration_blocks" in metrics
