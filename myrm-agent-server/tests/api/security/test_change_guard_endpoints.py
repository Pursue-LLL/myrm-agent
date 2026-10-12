"""Integration tests for ChangeGuard API endpoints.

[INPUT]
- HTTP requests to /api/v1/security/change-guard/* endpoints.

[OUTPUT]
- Verified JSON responses matching ChangeGuard DTO schemas (WS1-WS5).

[POS]
- Server integration test layer for review decision lanes and evidence hardening.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.change_guard_router import (
    router as change_guard_router,
)
from app.services.security.change_guard_service import (
    ChangeGuardService,
    get_change_guard_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> ChangeGuardService:
    """Fixture providing isolated in-memory service instance."""
    return ChangeGuardService()


@pytest.fixture(scope="function")
def client(isolated_service: ChangeGuardService) -> TestClient:
    """Fixture providing test client mounting change_guard_router."""
    test_app = FastAPI(title="Change Guard Test App")
    test_app.dependency_overrides[get_change_guard_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        change_guard_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_evaluate_endpoint_clean_pass(client: TestClient) -> None:
    payload = {
        "findings": [],
        "fail_on_authority_change": None,
        "enforce_definition_review_floor": True,
        "strict_exceptions": False,
        "exceptions": [],
    }
    resp = client.post(
        "/api/v1/security/change-guard/evaluate",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_outcome"] == "pass"
    assert data["lane_a"]["outcome"] == "pass"
    assert data["lane_b"]["outcome"] == "pass"
    assert data["lane_a"]["findings"] == []
    assert data["lane_b"]["findings"] == []


def test_evaluate_endpoint_blocking_lane_a(client: TestClient) -> None:
    payload = {
        "findings": [
            {
                "finding_id": "FIND-API-01",
                "rule_id": "ENV_SECRET_EXPOSURE",
                "category": "security",
                "target_object": "config.yaml",
                "change_class": "HIGH_RISK_CHANGE",
                "provenance_class": "detected",
                "gateability": "deterministic",
                "evidence": {
                    "evidence_type": "static-config",
                    "source_file": "config.yaml",
                    "description": "Exposed API key",
                },
                "message": "Secret token found in plain text",
            }
        ],
        "fail_on_authority_change": None,
        "enforce_definition_review_floor": True,
    }
    resp = client.post(
        "/api/v1/security/change-guard/evaluate",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_outcome"] == "block"
    assert data["lane_a"]["outcome"] == "block"
    assert len(data["lane_a"]["findings"]) == 1


def test_evaluate_endpoint_mandatory_review_lane_b(client: TestClient) -> None:
    payload = {
        "findings": [
            {
                "finding_id": "FIND-API-02",
                "rule_id": "GOV_AUTONOMY",
                "category": "governance",
                "target_object": "workflow.yaml",
                "change_class": "LOW_CHANGE",
                "provenance_class": "declared",
                "gateability": "review-only",
                "evidence": {
                    "evidence_type": "static-config",
                    "source_file": "workflow.yaml",
                    "description": "Autonomous execution enabled",
                },
                "message": "Autonomous execution flag requires governance signoff",
            }
        ]
    }
    resp = client.post(
        "/api/v1/security/change-guard/evaluate",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_outcome"] == "review-required"
    assert data["lane_b"]["outcome"] == "review-required"
    assert len(data["lane_b"]["unresolved_questions"]) == 1


def test_evaluate_endpoint_with_active_exception(client: TestClient) -> None:
    payload = {
        "findings": [
            {
                "finding_id": "FIND-API-03",
                "rule_id": "ENV_SECRET_EXPOSURE",
                "category": "security",
                "target_object": "dev.env",
                "change_class": "HIGH_RISK_CHANGE",
                "provenance_class": "detected",
                "gateability": "deterministic",
                "evidence": {
                    "evidence_type": "static-config",
                    "source_file": "dev.env",
                    "description": "Dev token",
                },
                "message": "Dev secret token",
            }
        ],
        "exceptions": [
            {
                "exception_id": "EXC-API-01",
                "finding_or_rule_id": "ENV_SECRET_EXPOSURE",
                "scope": "dev.env",
                "risk_owner": "sec-ops@company.com",
                "rationale": "Mock secret in dev environment only",
                "compensating_controls": "VPC sandbox isolation",
                "expires_at": "2026-12-31T23:59:59Z",
                "review_trigger": "manual",
            }
        ],
        "current_time_iso": "2026-06-01T00:00:00Z",
    }
    resp = client.post(
        "/api/v1/security/change-guard/evaluate",
        json=payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["overall_outcome"] == "pass"
    assert "EXC-API-01" in data["applied_exceptions"]


def test_config_endpoint(client: TestClient) -> None:
    resp = client.get("/api/v1/security/change-guard/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "MATERIAL_CHANGE" in data["supported_change_classes"]
    assert "static-config" in data["supported_evidence_types"]
    assert "PROMPT_" in data["definition_prefixes"]
