"""API endpoint tests for PreToolUse Hook Interceptor & API Key Precedence in myrm-agent-server."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.pre_tool_use_interceptor import (
    PreToolUseHookInterceptor,
)

from app.api.security.pre_tool_use_interceptor_router import (
    router as pre_tool_use_interceptor_router,
)
from app.services.security.pre_tool_use_interceptor_service import (
    PreToolUseInterceptorService,
    get_pre_tool_use_interceptor_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    interceptor = PreToolUseHookInterceptor()
    service = PreToolUseInterceptorService(interceptor=interceptor)

    app.dependency_overrides[get_pre_tool_use_interceptor_service] = lambda: service
    app.include_router(pre_tool_use_interceptor_router, prefix="/api/v1/security")
    return TestClient(app)


def test_intercept_tool_api(client: TestClient) -> None:
    # 1. Allowed command
    resp_allow = client.post(
        "/api/v1/security/pre-tool-use-interceptor/intercept",
        json={"tool_name": "run_command", "payload_str": "git status"},
    )
    assert resp_allow.status_code == 200
    assert resp_allow.json()["verdict"] == "ALLOW"

    # 2. Blocked command (normal response)
    resp_block = client.post(
        "/api/v1/security/pre-tool-use-interceptor/intercept",
        json={
            "tool_name": "run_command",
            "payload_str": "git push origin main",
            "raise_on_block": False,
        },
    )
    assert resp_block.status_code == 200
    data_block = resp_block.json()
    assert data_block["verdict"] == "BLOCK"
    assert data_block["rule_category"] == "PROTECTED_BRANCH_PUSH"
    assert data_block["blocked_rule_id"] == "RULE-PROT-BRANCH"

    # 3. Blocked command with raise_on_block=True -> HTTP 403
    resp_raise = client.post(
        "/api/v1/security/pre-tool-use-interceptor/intercept",
        json={
            "tool_name": "run_command",
            "payload_str": "git push origin main",
            "raise_on_block": True,
        },
    )
    assert resp_raise.status_code == 403
    assert "PROTECTED_BRANCH_PUSH" in resp_raise.json()["detail"]


def test_detect_key_conflict_api(client: TestClient) -> None:
    # Conflict case
    resp_conf = client.post(
        "/api/v1/security/pre-tool-use-interceptor/detect-key-conflict",
        json={
            "active_provider": "anthropic",
            "is_subscription_route": True,
            "env_dict": {"ANTHROPIC_API_KEY": "sk-ant-test"},
        },
    )
    assert resp_conf.status_code == 200
    data_conf = resp_conf.json()
    assert data_conf["has_conflict"] is True
    assert "ANTHROPIC_API_KEY" in data_conf["detected_env_vars"]

    # Clean case
    resp_clean = client.post(
        "/api/v1/security/pre-tool-use-interceptor/detect-key-conflict",
        json={
            "active_provider": "anthropic",
            "is_subscription_route": True,
            "env_dict": {},
        },
    )
    assert resp_clean.status_code == 200
    assert resp_clean.json()["has_conflict"] is False


def test_rules_catalog_and_toggle_api(client: TestClient) -> None:
    # 1. Get rules
    resp_rules = client.get("/api/v1/security/pre-tool-use-interceptor/rules")
    assert resp_rules.status_code == 200
    rules = resp_rules.json()
    assert len(rules) >= 4

    # 2. Toggle rule
    toggle_resp = client.post(
        "/api/v1/security/pre-tool-use-interceptor/rules/toggle",
        json={"rule_id": "RULE-PROT-BRANCH", "enabled": False},
    )
    assert toggle_resp.status_code == 200
    assert toggle_resp.json()["enabled"] is False

    # Verify now allowed
    resp_now_allow = client.post(
        "/api/v1/security/pre-tool-use-interceptor/intercept",
        json={"tool_name": "run_command", "payload_str": "git push origin main"},
    )
    assert resp_now_allow.json()["verdict"] == "ALLOW"

    # Re-enable
    client.post(
        "/api/v1/security/pre-tool-use-interceptor/rules/toggle",
        json={"rule_id": "RULE-PROT-BRANCH", "enabled": True},
    )

    # 3. Nonexistent rule toggle -> 404
    missing_toggle = client.post(
        "/api/v1/security/pre-tool-use-interceptor/rules/toggle",
        json={"rule_id": "RULE-NONEXISTENT", "enabled": True},
    )
    assert missing_toggle.status_code == 404
