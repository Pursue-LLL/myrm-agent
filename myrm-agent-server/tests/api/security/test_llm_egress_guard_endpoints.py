"""Integration tests for LLM Egress Default-Deny & Credential Binding endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.llm_egress_guard_router import (
    router as llm_egress_guard_router,
)
from app.services.security.llm_egress_guard_service import (
    LlmEgressGuardService,
    get_llm_egress_guard_service,
)


@pytest.fixture(scope="function")
def isolated_service() -> LlmEgressGuardService:
    """Fixture providing fresh in-memory service."""
    return LlmEgressGuardService()


@pytest.fixture(scope="function")
def client(isolated_service: LlmEgressGuardService) -> TestClient:
    """Fixture providing test client mounting llm_egress_guard_router with isolated service."""
    test_app = FastAPI(title="LLM Egress Guard Test App")
    test_app.dependency_overrides[get_llm_egress_guard_service] = (
        lambda: isolated_service
    )
    test_app.include_router(
        llm_egress_guard_router, prefix="/api/v1/security"
    )
    return TestClient(test_app, raise_server_exceptions=False)


def test_egress_fail_closed_without_policy(client: TestClient) -> None:
    # 1. GET policy returns 404 when not configured
    get_resp = client.get("/api/v1/security/llm-egress-guard/policy")
    assert get_resp.status_code == 404

    # 2. Evaluate egress without policy returns BLOCKED_NO_POLICY
    eval_payload: dict[str, str] = {
        "target_url_or_domain": "https://api.openai.com/v1/chat/completions",
        "presented_credential_id": "cred-openai-prod",
    }
    resp = client.post(
        "/api/v1/security/llm-egress-guard/evaluate",
        json=eval_payload,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_permitted"] is False
    assert data["verdict"] == "BLOCKED_NO_POLICY"


def test_set_policy_and_evaluation_matrix(client: TestClient) -> None:
    # 1. Set explicit policy
    policy_payload: dict[str, object] = {
        "policy_id": "pol-sec-001",
        "is_default_deny": True,
        "allowed_rules": [
            {
                "rule_id": "RULE-OPENAI",
                "domain_pattern": "api.openai.com",
                "bound_credential_ids": ["cred-openai-prod"],
                "description": "OpenAI official endpoints",
                "require_credential_binding": True,
            },
            {
                "rule_id": "RULE-ANTHROPIC",
                "domain_pattern": "*.anthropic.com",
                "bound_credential_ids": ["cred-claude-prod"],
                "description": "Anthropic Claude endpoints",
                "require_credential_binding": True,
            },
        ],
    }
    set_resp = client.post(
        "/api/v1/security/llm-egress-guard/policy",
        json=policy_payload,
    )
    assert set_resp.status_code == 200
    data = set_resp.json()
    assert data["policy_id"] == "pol-sec-001"
    assert data["is_default_deny"] is True

    # 2. Evaluate allowed outbound request
    eval_ok = client.post(
        "/api/v1/security/llm-egress-guard/evaluate",
        json={
            "target_url_or_domain": "https://api.openai.com/v1/models",
            "presented_credential_id": "cred-openai-prod",
        },
    )
    assert eval_ok.status_code == 200
    assert eval_ok.json()["is_permitted"] is True
    assert eval_ok.json()["verdict"] == "PERMITTED"

    # 3. Evaluate credential mismatch
    eval_mismatch = client.post(
        "/api/v1/security/llm-egress-guard/evaluate",
        json={
            "target_url_or_domain": "https://api.openai.com/v1/models",
            "presented_credential_id": "cred-claude-prod",
        },
    )
    assert eval_mismatch.status_code == 200
    assert eval_mismatch.json()["is_permitted"] is False
    assert eval_mismatch.json()["verdict"] == "BLOCKED_CREDENTIAL_MISMATCH"

    # 4. Evaluate unwhitelisted destination
    eval_blocked_domain = client.post(
        "/api/v1/security/llm-egress-guard/evaluate",
        json={
            "target_url_or_domain": "https://malicious-site.example.com",
            "presented_credential_id": "cred-openai-prod",
        },
    )
    assert eval_blocked_domain.status_code == 200
    assert eval_blocked_domain.json()["is_permitted"] is False
    assert (
        eval_blocked_domain.json()["verdict"]
        == "BLOCKED_DOMAIN_NOT_ALLOWED"
    )

    # 5. Clear policy returns to fail-closed
    del_resp = client.delete("/api/v1/security/llm-egress-guard/policy")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

    eval_after_del = client.post(
        "/api/v1/security/llm-egress-guard/evaluate",
        json={
            "target_url_or_domain": "https://api.openai.com/v1/models",
            "presented_credential_id": "cred-openai-prod",
        },
    )
    assert eval_after_del.status_code == 200
    assert eval_after_del.json()["is_permitted"] is False
    assert eval_after_del.json()["verdict"] == "BLOCKED_NO_POLICY"
