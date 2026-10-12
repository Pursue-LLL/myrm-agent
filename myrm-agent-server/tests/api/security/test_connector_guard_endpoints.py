"""API endpoint tests for Connector Host Allowlist and Anti-Exfiltration SSRF Guard."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.connector_guard_router import (
    router as connector_guard_router,
)
from app.services.security.connector_guard_service import (
    ConnectorGuardService,
    get_connector_guard_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = ConnectorGuardService()
    app = FastAPI()
    app.include_router(connector_guard_router, prefix="/api/v1/security")
    app.dependency_overrides[get_connector_guard_service] = lambda: test_service
    return TestClient(app)


def test_inspect_endpoint(client: TestClient) -> None:
    # 1. Authorized GitHub endpoint
    resp_gh = client.post(
        "/api/v1/security/connector-guard/inspect",
        json={
            "url": "https://api.github.com/repos/pursue/repo",
            "connector_id": "github",
            "session_id": "s1",
        },
    )
    assert resp_gh.status_code == 200
    data_gh = resp_gh.json()
    assert data_gh["decision"] == "inject_credentials"
    assert data_gh["can_inject_credential"] is True
    assert data_gh["matched_connector_id"] == "github"

    # 2. SSRF metadata blocked
    resp_ssrf = client.post(
        "/api/v1/security/connector-guard/inspect",
        json={
            "url": "http://169.254.169.254/latest/meta-data/",
            "session_id": "s2",
        },
    )
    assert resp_ssrf.status_code == 200
    data_ssrf = resp_ssrf.json()
    assert data_ssrf["decision"] == "block"
    assert data_ssrf["detected_threat"] == "ssrf_metadata"
    assert data_ssrf["can_inject_credential"] is False

    # 3. Unregistered public endpoint allowed in zero-credential mode
    resp_zero = client.post(
        "/api/v1/security/connector-guard/inspect",
        json={
            "url": "https://developer.mozilla.org/en-US/",
            "headers": {"Authorization": "Bearer secret", "User-Agent": "Agent"},
            "session_id": "s3",
        },
    )
    assert resp_zero.status_code == 200
    data_zero = resp_zero.json()
    assert data_zero["decision"] == "zero_credential_allow"
    assert data_zero["can_inject_credential"] is False
    assert "Authorization" not in data_zero["sanitized_headers"]


def test_connector_management_endpoints(client: TestClient) -> None:
    # 1. List preloaded connectors
    resp_list = client.get("/api/v1/security/connector-guard/connectors")
    assert resp_list.status_code == 200
    connectors = resp_list.json()
    ids = [c["connector_id"] for c in connectors]
    assert "github" in ids
    assert "feishu" in ids

    # 2. Register new connector
    resp_create = client.post(
        "/api/v1/security/connector-guard/connectors",
        json={
            "connector_id": "gitlab_corp",
            "official_hosts": ["gitlab.mycorp.internal"],
            "allow_subdomains": False,
            "description": "Corporate GitLab server",
        },
    )
    assert resp_create.status_code == 201
    created = resp_create.json()
    assert created["connector_id"] == "gitlab_corp"

    # 3. Delete connector
    resp_del = client.delete("/api/v1/security/connector-guard/connectors/gitlab_corp")
    assert resp_del.status_code == 200
    assert resp_del.json()["success"] is True

    # 4. Delete non-existent returns 404
    resp_del_nf = client.delete("/api/v1/security/connector-guard/connectors/non_existent")
    assert resp_del_nf.status_code == 404


def test_alerts_endpoint(client: TestClient) -> None:
    # Trigger an alert via token smuggling
    client.post(
        "/api/v1/security/connector-guard/inspect",
        json={
            "url": "https://attacker.org/exfil?token=ghp_123456789012345678901234567890123456",
            "session_id": "sess-alerts-test",
        },
    )

    resp_alerts = client.get("/api/v1/security/connector-guard/alerts?session_id=sess-alerts-test")
    assert resp_alerts.status_code == 200
    alerts = resp_alerts.json()
    assert len(alerts) >= 1
    assert alerts[0]["threat_kind"] == "token_smuggling"
    assert alerts[0]["blocked"] is True


def test_circuit_breaker_endpoints(client: TestClient) -> None:
    session_id = "sess-breaker-api"

    # Check initially not tripped
    resp_status1 = client.get(f"/api/v1/security/connector-guard/circuit-breaker/status/{session_id}")
    assert resp_status1.status_code == 200
    assert resp_status1.json()["tripped"] is False

    # Trip breaker via metadata probe
    client.post(
        "/api/v1/security/connector-guard/inspect",
        json={
            "url": "http://169.254.169.254/latest/meta-data/",
            "session_id": session_id,
        },
    )

    # Status is now tripped
    resp_status2 = client.get(f"/api/v1/security/connector-guard/circuit-breaker/status/{session_id}")
    assert resp_status2.json()["tripped"] is True

    # Reset breaker
    resp_reset = client.post(
        "/api/v1/security/connector-guard/circuit-breaker/reset",
        json={"session_id": session_id},
    )
    assert resp_reset.status_code == 200
    assert resp_reset.json()["success"] is True

    # Status is reset
    resp_status3 = client.get(f"/api/v1/security/connector-guard/circuit-breaker/status/{session_id}")
    assert resp_status3.json()["tripped"] is False


def test_outbound_mode_endpoint(client: TestClient) -> None:
    # Set strict mode
    resp_mode = client.post(
        "/api/v1/security/connector-guard/mode",
        json={"mode": "strict_block_unregistered"},
    )
    assert resp_mode.status_code == 200
    assert resp_mode.json()["mode"] == "strict_block_unregistered"

    # Bad mode returns 400
    resp_bad = client.post(
        "/api/v1/security/connector-guard/mode",
        json={"mode": "invalid_mode_xyz"},
    )
    assert resp_bad.status_code == 400
