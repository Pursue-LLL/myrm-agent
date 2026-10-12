"""API endpoint tests for Multi-Tenant Data Isolation and Cross-Contamination Probes."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.data_isolation_probe_router import (
    router as data_isolation_probe_router,
)
from app.services.security.data_isolation_probe_service import (
    DataIsolationProbeService,
    get_data_isolation_probe_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = DataIsolationProbeService(enforce_strict_clean=True)
    app = FastAPI()
    app.include_router(data_isolation_probe_router, prefix="/api/v1/security")
    app.dependency_overrides[get_data_isolation_probe_service] = (
        lambda: test_service
    )
    return TestClient(app)


def test_compile_partition_key_endpoint(client: TestClient) -> None:
    """Test compiling partition key through REST endpoint."""
    resp = client.post(
        "/api/v1/security/isolation-probes/compile-partition",
        json={
            "context": {
                "user_id": "tenant_123",
                "agent_id": "agent_alpha",
                "scope": "agent",
            }
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["composite_key"] == "usr_tenant_123::agt_agent_alpha::scp_agent"
    assert data["user_id"] == "tenant_123"
    assert data["agent_id"] == "agent_alpha"
    assert len(data["namespace_digest"]) == 16


def test_run_isolation_audit_endpoint(client: TestClient) -> None:
    """Test running synthetic cross-tenant adversarial isolation audit via API."""
    resp = client.post(
        "/api/v1/security/isolation-probes/run-audit",
        json={
            "context": {
                "user_id": "tenant_enterprise_xyz",
                "agent_id": "auditor_bot",
                "scope": "agent",
            },
            "environment_type": "cloud_dedicated_sandbox",
        },
    )
    assert resp.status_code == 200
    report = resp.json()

    assert report["is_safe"] is True
    assert report["total_probes_run"] >= 4
    assert report["cross_hits_count"] == 0
    assert report["isolation_pass_rate"] == 100.0
    assert report["environment_type"] == "cloud_dedicated_sandbox"
    assert report["partition_integrity_verified"] is True
    assert "Zero cross-contamination confirmed" in report["summary"]

    # Verify scenario breakdown
    scenarios = report["scenario_results"]
    assert len(scenarios) >= 4
    for sc in scenarios:
        assert sc["is_isolated"] is True
        assert sc["cross_hits"] == 0
