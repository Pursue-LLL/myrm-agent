"""API endpoint tests for Admin Auth Surface in myrm-agent-server."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.admin_auth_surface import (
    AdminAuthSurfaceConfig,
    AdminAuthSurfaceManager,
    LoginMethodSettings,
    OAuthConnectionConfig,
    OAuthProviderType,
)

from app.api.security.admin_auth_surface_router import (
    router as admin_auth_surface_router,
)
from app.services.security.admin_auth_surface_service import (
    AdminAuthSurfaceService,
    get_admin_auth_surface_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    initial_config = AdminAuthSurfaceConfig(
        login_methods=LoginMethodSettings(
            password_enabled=True,
            email_code_enabled=False,
            email_code_auto_registration_enabled=False,
        ),
        oauth_connections=[
            OAuthConnectionConfig(
                id="gh_1",
                provider=OAuthProviderType.GITHUB,
                name="GitHub Login",
                client_id="client_gh_123",
                client_secret="secret_gh_very_secret",
                authorize_url="https://github.com/login/oauth/authorize",
                token_url="https://github.com/login/oauth/access_token",
                enabled=True,
            )
        ],
        allow_public_registration=True,
        mfa_enforced=False,
    )
    manager = AdminAuthSurfaceManager(initial_config=initial_config)
    service = AdminAuthSurfaceService(manager=manager)

    app.dependency_overrides[get_admin_auth_surface_service] = lambda: service
    app.include_router(admin_auth_surface_router, prefix="/api/v1/security")
    return TestClient(app)


def test_get_admin_auth_surface_api(client: TestClient) -> None:
    resp = client.get("/api/v1/security/admin-auth-surface/")
    assert resp.status_code == 200
    data = resp.json()

    assert data["login_methods"]["password_enabled"] is True
    assert len(data["oauth_connections"]) == 1
    oauth = data["oauth_connections"][0]
    assert oauth["id"] == "gh_1"
    # Secrets should be masked
    assert "****" in oauth["client_secret"]


def test_validate_admin_auth_surface_api(client: TestClient) -> None:
    # 1. Valid
    valid_payload = {
        "login_methods": {
            "password_enabled": True,
            "email_code_enabled": False,
            "email_code_auto_registration_enabled": False,
        },
        "oauth_connections": [],
        "allow_public_registration": False,
        "mfa_enforced": False,
    }
    resp_valid = client.post(
        "/api/v1/security/admin-auth-surface/validate",
        json=valid_payload,
    )
    assert resp_valid.status_code == 200
    res_data = resp_valid.json()
    assert res_data["is_valid"] is True
    assert res_data["active_login_method_count"] == 1
    assert len(res_data["errors"]) == 0

    # 2. Invalid (lockout)
    invalid_payload = {
        "login_methods": {
            "password_enabled": False,
            "email_code_enabled": False,
            "email_code_auto_registration_enabled": False,
        },
        "oauth_connections": [],
        "allow_public_registration": False,
        "mfa_enforced": False,
    }
    resp_invalid = client.post(
        "/api/v1/security/admin-auth-surface/validate",
        json=invalid_payload,
    )
    assert resp_invalid.status_code == 200
    inv_data = resp_invalid.json()
    assert inv_data["is_valid"] is False
    assert inv_data["active_login_method_count"] == 0
    assert len(inv_data["errors"]) > 0


def test_update_admin_auth_surface_success_api(client: TestClient) -> None:
    # Fetch masked config first
    get_resp = client.get("/api/v1/security/admin-auth-surface/")
    current = get_resp.json()

    update_payload = {
        "config": {
            "login_methods": {
                "password_enabled": True,
                "email_code_enabled": True,
                "email_code_auto_registration_enabled": True,
            },
            "oauth_connections": current["oauth_connections"],
            "allow_public_registration": True,
            "mfa_enforced": True,
        },
        "preserve_masked_secrets": True,
    }

    put_resp = client.put(
        "/api/v1/security/admin-auth-surface/",
        json=update_payload,
    )
    assert put_resp.status_code == 200
    result = put_resp.json()
    assert result["validation"]["is_valid"] is True
    assert result["config"]["login_methods"]["email_code_enabled"] is True
    assert result["config"]["mfa_enforced"] is True


def test_update_admin_auth_surface_lockout_rejected_api(
    client: TestClient,
) -> None:
    bad_payload = {
        "config": {
            "login_methods": {
                "password_enabled": False,
                "email_code_enabled": False,
                "email_code_auto_registration_enabled": False,
            },
            "oauth_connections": [],
            "allow_public_registration": False,
            "mfa_enforced": False,
        },
        "preserve_masked_secrets": True,
    }
    resp = client.put(
        "/api/v1/security/admin-auth-surface/",
        json=bad_payload,
    )
    assert resp.status_code == 400
    assert "Deadlock condition" in resp.json()["detail"]


def test_service_disk_persistence(tmp_path: Path) -> None:
    storage_file = tmp_path / "admin_auth_surface.json"
    svc1 = AdminAuthSurfaceService(storage_path=storage_file)

    # Initial state
    cfg1 = svc1.get_auth_surface()
    assert cfg1.login_methods.password_enabled is True
    assert cfg1.login_methods.email_code_enabled is False

    # Update state via svc1
    from app.schemas.admin_auth_surface import (
        AdminAuthSurfaceConfigDto,
        LoginMethodSettingsDto,
        UpdateAuthSurfaceRequest,
    )

    update_req = UpdateAuthSurfaceRequest(
        config=AdminAuthSurfaceConfigDto(
            login_methods=LoginMethodSettingsDto(
                password_enabled=True,
                email_code_enabled=True,
                email_code_auto_registration_enabled=True,
            ),
            oauth_connections=[],
            allow_public_registration=False,
            mfa_enforced=True,
        ),
        preserve_masked_secrets=True,
    )
    svc1.update_auth_surface(update_req)

    # Instantiate svc2 pointing to same file, simulating restart
    svc2 = AdminAuthSurfaceService(storage_path=storage_file)
    cfg2 = svc2.get_auth_surface()
    assert cfg2.login_methods.email_code_enabled is True
    assert cfg2.mfa_enforced is True
