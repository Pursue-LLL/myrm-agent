"""
[POS] tests/api/security/test_policy_conformance_endpoints.py
Integration tests for Agent Policy Conformance & Message Routing REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.policy_conformance_router import (
    router as policy_conformance_router,
)
from app.services.security.policy_conformance_service import (
    PolicyConformanceService,
    get_policy_conformance_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = PolicyConformanceService()
    app = FastAPI()
    app.include_router(policy_conformance_router)
    app.dependency_overrides[get_policy_conformance_service] = lambda: service
    return TestClient(app)


def test_endpoint_baseline_crud(client: TestClient) -> None:
    """Test GET and PUT baseline endpoints."""
    resp = client.get("/policy-conformance/baseline")
    assert resp.status_code == 200
    data = resp.json()
    assert data["baseline_id"] == "default-baseline-2026"
    assert "openai" in data["allowed_model_providers"]

    updated_payload = {
        "baseline_id": "enterprise-secops-2026",
        "allowed_model_providers": ["anthropic", "deepseek"],
        "allowed_mcp_servers": ["memory", "calculator"],
        "prohibited_domains": ["*.onion", "darknet.internal"],
        "max_temperature": 0.7,
        "enforce_approval_gate": True,
    }
    put_resp = client.put("/policy-conformance/baseline", json=updated_payload)
    assert put_resp.status_code == 200
    put_data = put_resp.json()
    assert put_data["baseline_id"] == "enterprise-secops-2026"
    assert "openai" not in put_data["allowed_model_providers"]


def test_endpoint_audit_and_remediate(client: TestClient) -> None:
    """Test POST /audit and POST /remediate endpoints."""
    audit_payload = {
        "agents": [
            {
                "agent_id": "compliant-agent",
                "model_provider": "openai",
                "loaded_mcp_servers": ["memory"],
                "configured_egress_domains": ["api.example.com"],
                "temperature": 0.5,
                "approval_gate_enabled": True,
            },
            {
                "agent_id": "drifting-agent",
                "model_provider": "unapproved-provider",
                "loaded_mcp_servers": ["rogue-mcp"],
                "configured_egress_domains": ["c2.darknet.internal"],
                "temperature": 1.2,
                "approval_gate_enabled": False,
            },
        ]
    }
    audit_resp = client.post("/policy-conformance/audit", json=audit_payload)
    assert audit_resp.status_code == 200
    audit_data = audit_resp.json()
    assert audit_data["conformance_score"] < 100
    assert len(audit_data["findings"]) >= 4

    remediate_payload = {
        "config": {
            "agent_id": "drifting-agent",
            "model_provider": "unapproved-provider",
            "loaded_mcp_servers": ["memory", "rogue-mcp"],
            "configured_egress_domains": ["c2.darknet.internal"],
            "temperature": 1.5,
            "approval_gate_enabled": False,
        }
    }
    rem_resp = client.post("/policy-conformance/remediate", json=remediate_payload)
    assert rem_resp.status_code == 200
    rem_data = rem_resp.json()["remediated_config"]
    assert rem_data["model_provider"] == "openai"
    assert "rogue-mcp" not in rem_data["loaded_mcp_servers"]
    assert len(rem_data["configured_egress_domains"]) == 0
    assert rem_data["temperature"] <= 1.0
    assert rem_data["approval_gate_enabled"] is True


def test_endpoint_verify_routing(client: TestClient) -> None:
    """Test POST /verify-routing endpoint."""
    routing_payload = {
        "rules": [
            {
                "agent_id": "finance-analyst",
                "keywords": ["finance", "revenue", "stock"],
                "intent_tags": ["accounting"],
            }
        ],
        "test_cases": [
            {
                "case_id": "case-fin-01",
                "sample_message": "Calculate total annual revenue",
                "expected_agent_id": "finance-analyst",
                "required_keywords": ["revenue"],
            }
        ],
    }
    resp = client.post("/policy-conformance/verify-routing", json=routing_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["pass_rate"] == 100.0
    assert len(data["results"]) == 1
    assert data["results"][0]["is_matched"] is True
    assert data["results"][0]["routed_agent_id"] == "finance-analyst"


def test_endpoint_full_audit_and_metrics(client: TestClient) -> None:
    """Test POST /full-audit and GET /metrics endpoints."""
    full_payload = {
        "agents": [
            {
                "agent_id": "audit-agent-01",
                "model_provider": "openai",
                "loaded_mcp_servers": ["memory"],
                "configured_egress_domains": [],
                "temperature": 0.5,
                "approval_gate_enabled": True,
            }
        ],
        "rules": [
            {
                "agent_id": "audit-agent-01",
                "keywords": ["system", "audit"],
                "intent_tags": ["auditing"],
            }
        ],
        "test_cases": [
            {
                "case_id": "tc-audit-1",
                "sample_message": "Run system audit verification",
                "expected_agent_id": "audit-agent-01",
                "required_keywords": ["audit"],
            }
        ],
    }
    resp = client.post("/policy-conformance/full-audit", json=full_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["conformance_score"] == 100
    assert data["routing_pass_rate"] == 100.0
    assert "🛡️ 策略合规评分: 100/100" in data["summary_badge"]

    metrics_resp = client.get("/policy-conformance/metrics")
    assert metrics_resp.status_code == 200
    metrics = metrics_resp.json()
    assert metrics["audits_executed_total"] >= 1
    assert metrics["agents_audited_total"] >= 1
    assert metrics["routing_checks_run_total"] >= 1
    assert metrics["routing_checks_passed_total"] >= 1
