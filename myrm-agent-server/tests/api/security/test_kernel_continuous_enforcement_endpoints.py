"""Integration tests for Kernel Continuous Enforcement REST endpoints.

[POS] tests/api/security/test_kernel_continuous_enforcement_endpoints.py
[INPUT] app.api.security.kernel_continuous_enforcement_router, app.services.security.kernel_continuous_enforcement_service
[OUTPUT] End-to-end integration tests for 3D continuous enforcement, formal prover gates,
and revocation residue audits.
Strict typing applied: No `Any` types allowed. Enforced under 400 lines limit.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.kernel_continuous_enforcement_router import (
    get_enforcement_service,
    kernel_continuous_enforcement_router,
)
from app.services.security.kernel_continuous_enforcement_service import (
    KernelContinuousEnforcementService,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = KernelContinuousEnforcementService()
    app = FastAPI()
    app.include_router(kernel_continuous_enforcement_router, prefix="/api/security")
    app.dependency_overrides[get_enforcement_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_egress_and_rules_lifecycle(client: TestClient) -> None:
    # 1. Initially no matching rules -> deny
    eval_init_payload = {
        "binary_name": "curl",
        "host": "api.service.internal",
        "port": 8443,
        "path": "/v1/metrics",
        "protocol": "rest",
        "has_upgrade_header": False,
    }
    resp_init = client.post("/api/security/kernel-continuous-enforcement/evaluate", json=eval_init_payload)
    assert resp_init.status_code == 200
    assert resp_init.json()["decision"] == "deny"

    # 2. Add 3D rule
    rule_payload = {
        "rule_id": "rule-metrics-api",
        "allowed_binaries": ["curl", "prometheus-agent"],
        "endpoint_host": "api.service.internal",
        "endpoint_port": 8443,
        "path_glob": "/v1/*",
        "protocol": "rest",
        "allow_upgrade_header": False,
        "provider_binding": None,
    }
    resp_add = client.post("/api/security/kernel-continuous-enforcement/rules", json=rule_payload)
    assert resp_add.status_code == 201
    assert resp_add.json()["rule_id"] == "rule-metrics-api"

    # 3. Verify rule is active
    resp_rules = client.get("/api/security/kernel-continuous-enforcement/rules")
    assert resp_rules.status_code == 200
    rules_list = resp_rules.json()
    assert len(rules_list) == 1
    assert rules_list[0]["rule_id"] == "rule-metrics-api"

    # 4. Re-evaluate with authorized binary -> allow
    resp_allow = client.post("/api/security/kernel-continuous-enforcement/evaluate", json=eval_init_payload)
    assert resp_allow.status_code == 200
    assert resp_allow.json()["decision"] == "allow"
    assert resp_allow.json()["rule_id"] == "rule-metrics-api"

    # 5. Evaluate with unauthorized binary -> deny
    eval_unauth_payload = dict(eval_init_payload)
    eval_unauth_payload["binary_name"] = "bash"
    resp_unauth = client.post("/api/security/kernel-continuous-enforcement/evaluate", json=eval_unauth_payload)
    assert resp_unauth.status_code == 200
    assert resp_unauth.json()["decision"] == "deny"


def test_endpoint_proposals_lifecycle(client: TestClient) -> None:
    # 1. Submit proposal with a risky rule
    proposal_payload = {
        "proposal_id": "prop-test-01",
        "agent_id": "agent-orchestrator",
        "proposed_rules": [
            {
                "rule_id": "prop-rule-1",
                "allowed_binaries": ["*"],
                "endpoint_host": "cluster.mgmt.internal",
                "endpoint_port": 6443,
                "path_glob": "*",
                "protocol": "tcp",
                "allow_upgrade_header": False,
                "provider_binding": None,
            }
        ],
        "justification": "Access Kubernetes API cluster",
    }
    resp_prop = client.post("/api/security/kernel-continuous-enforcement/proposals", json=proposal_payload)
    assert resp_prop.status_code == 201
    proof_data = resp_prop.json()
    assert proof_data["is_safe"] is False
    assert proof_data["requires_human_approval"] is True
    assert len(proof_data["flagged_risks"]) >= 2

    # 2. List proposals
    resp_list = client.get("/api/security/kernel-continuous-enforcement/proposals")
    assert resp_list.status_code == 200
    props = resp_list.json()
    assert len(props) == 1
    assert props[0]["status"] == "PENDING"

    # 3. Approve proposal
    resp_approve = client.post("/api/security/kernel-continuous-enforcement/proposals/prop-test-01/approve")
    assert resp_approve.status_code == 200
    assert resp_approve.json()["status"] == "approved"

    # 4. Verify rule was hot-loaded
    resp_rules = client.get("/api/security/kernel-continuous-enforcement/rules")
    assert resp_rules.status_code == 200
    assert any(r["rule_id"] == "prop-rule-1" for r in resp_rules.json())


def test_endpoint_revocation_audit_lifecycle(client: TestClient) -> None:
    # 1. Execute audit with lingering artifacts
    audit_payload = {
        "run_id": "run-sandboxed-55",
        "active_pids": [12345],
        "open_sockets": ["10.0.0.1:443"],
        "temp_files": ["/tmp/.session_key"],
        "cached_tokens": ["token_live_123"],
    }
    resp_audit = client.post("/api/security/kernel-continuous-enforcement/revocation/audit", json=audit_payload)
    assert resp_audit.status_code == 201
    report = resp_audit.json()
    assert report["run_id"] == "run-sandboxed-55"
    assert report["is_fully_clean"] is False
    assert len(report["lingering_pids"]) == 1

    # 2. Retrieve history of reports
    resp_reports = client.get("/api/security/kernel-continuous-enforcement/revocation/reports")
    assert resp_reports.status_code == 200
    reports_list = resp_reports.json()
    assert len(reports_list) == 1
    assert reports_list[0]["run_id"] == "run-sandboxed-55"
