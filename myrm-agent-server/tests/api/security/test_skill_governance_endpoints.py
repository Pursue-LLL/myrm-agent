"""Integration tests for Skill Governance API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.skill_governance_router import router as skill_governance_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting skill_governance_router."""
    test_app = FastAPI(title="Skill Governance Test App")
    test_app.include_router(skill_governance_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_parse_contract_endpoint(client: TestClient) -> None:
    content = (
        "---\n"
        "tools:\n"
        "  - web_search\n"
        "  - bash\n"
        "network_egress: true\n"
        "filesystem_scope: full_access\n"
        "---\n"
        "# Shell Executor Skill\n"
    )

    resp = client.post(
        "/api/v1/security/skill-governance/parse-contract",
        json={
            "content": content,
            "skill_name": "shell_exec_skill",
            "version": "1.0.0",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_name"] == "shell_exec_skill"
    assert "bash" in data["declared_tools"]
    assert data["network_egress"] is True
    assert data["filesystem_scope"] == "full_access"
    assert data["requires_admin_review"] is True


def test_diff_contracts_endpoint(client: TestClient) -> None:
    base = {
        "skill_name": "linter_skill",
        "version": "1.0.0",
        "declared_tools": ["file_read"],
        "network_egress": False,
        "filesystem_scope": "read_only",
        "requires_admin_review": False,
    }
    target = {
        "skill_name": "linter_skill",
        "version": "1.1.0",
        "declared_tools": ["file_read", "bash"],
        "network_egress": True,
        "filesystem_scope": "task_workspace",
        "requires_admin_review": True,
    }

    resp = client.post(
        "/api/v1/security/skill-governance/diff-contracts",
        json={
            "base_contract": base,
            "target_contract": target,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["skill_name"] == "linter_skill"
    assert data["has_privilege_escalation"] is True
    assert data["review_required"] is True
    assert "bash" in data["added_tools"]


def test_validate_mounting_endpoint(client: TestClient) -> None:
    contract = {
        "skill_name": "elevated_skill",
        "version": "1.0.0",
        "declared_tools": ["bash_code_execute"],
        "network_egress": True,
        "filesystem_scope": "full_access",
        "requires_admin_review": True,
    }

    # 1. Unapproved mounting
    unapproved_resp = client.post(
        "/api/v1/security/skill-governance/validate-mounting",
        json={"contract": contract, "is_approved": False},
    )
    assert unapproved_resp.status_code == 200
    assert unapproved_resp.json()["permitted"] is False

    # 2. Approved mounting
    approved_resp = client.post(
        "/api/v1/security/skill-governance/validate-mounting",
        json={"contract": contract, "is_approved": True},
    )
    assert approved_resp.status_code == 200
    assert approved_resp.json()["permitted"] is True
