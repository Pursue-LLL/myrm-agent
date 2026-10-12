"""API endpoint tests for Sensitive Vault and Credential File Overwrite Deny Guard."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.sensitive_file_guard_router import (
    router as sensitive_file_guard_router,
)
from app.services.security.sensitive_file_guard_service import (
    SensitiveFileGuardService,
    get_sensitive_file_guard_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = SensitiveFileGuardService()
    app = FastAPI()
    app.include_router(sensitive_file_guard_router, prefix="/api/v1/security")
    app.dependency_overrides[get_sensitive_file_guard_service] = lambda: test_service
    return TestClient(app)


def test_inspect_endpoint(client: TestClient) -> None:
    # 1. Blocked .env file
    resp_env = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={
            "target_path": "/app/.env",
            "operation_type": "overwrite",
            "tool_name": "file_write",
            "session_id": "api-s1",
        },
    )
    assert resp_env.status_code == 200
    data_env = resp_env.json()
    assert data_env["allowed"] is False
    assert data_env["category"] == "env_secret"
    assert data_env["matched_rule_id"] == "env_files"
    assert data_env["is_unlocked"] is False

    # 2. Blocked private key
    resp_key = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={"target_path": "~/.ssh/id_rsa"},
    )
    assert resp_key.status_code == 200
    assert resp_key.json()["allowed"] is False
    assert resp_key.json()["category"] == "private_key"

    # 3. Blocked vault database
    resp_vault = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={"target_path": ".myrm/vault.db"},
    )
    assert resp_vault.status_code == 200
    assert resp_vault.json()["allowed"] is False
    assert resp_vault.json()["category"] == "password_vault"

    # 4. Safe source code file permitted
    resp_safe = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={"target_path": "src/services/user_service.py"},
    )
    assert resp_safe.status_code == 200
    assert resp_safe.json()["allowed"] is True
    assert resp_safe.json()["matched_rule_id"] is None


def test_unlock_and_revoke_endpoints(client: TestClient) -> None:
    target_file = "/workspace/.env.production"

    # 1. Issue temporary unlock token
    resp_unlock = client.post(
        "/api/v1/security/sensitive-file-guard/unlock",
        json={
            "target_path": target_file,
            "ttl_seconds": 300,
            "granted_by": "admin_ui_prompt",
        },
    )
    assert resp_unlock.status_code == 201
    grant = resp_unlock.json()
    token = grant["unlock_token"]
    assert token is not None

    # 2. List active grants
    resp_grants = client.get("/api/v1/security/sensitive-file-guard/grants")
    assert resp_grants.status_code == 200
    assert any(g["unlock_token"] == token for g in resp_grants.json())

    # 3. Write with unlock token succeeds
    resp_write_ok = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={
            "target_path": target_file,
            "operation_type": "replace",
            "unlock_token": token,
        },
    )
    assert resp_write_ok.status_code == 200
    assert resp_write_ok.json()["allowed"] is True
    assert resp_write_ok.json()["is_unlocked"] is True

    # 4. Revoke token
    resp_revoke = client.post(
        "/api/v1/security/sensitive-file-guard/revoke",
        json={"unlock_token": token},
    )
    assert resp_revoke.status_code == 200
    assert resp_revoke.json()["success"] is True

    # 5. Write blocked again after revocation
    resp_write_blocked = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={
            "target_path": target_file,
            "operation_type": "replace",
            "unlock_token": token,
        },
    )
    assert resp_write_blocked.status_code == 200
    assert resp_write_blocked.json()["allowed"] is False


def test_alerts_endpoint(client: TestClient) -> None:
    # Trigger blocked write
    client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={
            "target_path": "~/.aws/credentials",
            "session_id": "api-sess-alerts-test",
        },
    )

    resp_alerts = client.get(
        "/api/v1/security/sensitive-file-guard/alerts?session_id=api-sess-alerts-test"
    )
    assert resp_alerts.status_code == 200
    alerts = resp_alerts.json()
    assert len(alerts) >= 1
    assert alerts[0]["category"] == "cloud_credential"


def test_invalid_operation_type(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/sensitive-file-guard/inspect",
        json={
            "target_path": "test.txt",
            "operation_type": "invalid_operation_type_xyz",
        },
    )
    assert resp.status_code == 400
