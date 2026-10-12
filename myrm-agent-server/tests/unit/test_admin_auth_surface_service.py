"""Unit tests for AdminAuthSurfaceService in myrm-agent-server."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.admin_auth_surface import (
    AdminAuthSurfaceConfig,
    AdminAuthSurfaceManager,
    LoginMethodSettings,
    OAuthConnectionConfig,
    OAuthProviderType,
)

from app.schemas.admin_auth_surface import (
    AdminAuthSurfaceConfigDto,
    LoginMethodSettingsDto,
    OAuthConnectionDto,
    UpdateAuthSurfaceRequest,
)
from app.services.security.admin_auth_surface_service import (
    AdminAuthSurfaceService,
    get_admin_auth_surface_service,
)


@pytest.fixture
def service() -> AdminAuthSurfaceService:
    initial_config = AdminAuthSurfaceConfig(
        login_methods=LoginMethodSettings(
            password_enabled=True,
            email_code_enabled=False,
            email_code_auto_registration_enabled=False,
        ),
        oauth_connections=[
            OAuthConnectionConfig(
                id="github_oauth",
                provider=OAuthProviderType.GITHUB,
                name="GitHub Enterprise",
                client_id="gh_client_123",
                client_secret="gh_secret_super_secret_999",
                authorize_url="https://github.com/login/oauth/authorize",
                token_url="https://github.com/login/oauth/access_token",
                enabled=True,
            )
        ],
        allow_public_registration=True,
        mfa_enforced=False,
    )
    manager = AdminAuthSurfaceManager(initial_config=initial_config)
    return AdminAuthSurfaceService(manager=manager)


def test_get_auth_surface_masks_secrets(service: AdminAuthSurfaceService) -> None:
    config_dto = service.get_auth_surface(masked=True)
    assert config_dto.login_methods.password_enabled is True
    assert len(config_dto.oauth_connections) == 1
    conn = config_dto.oauth_connections[0]
    assert conn.id == "github_oauth"
    assert conn.client_secret.startswith("gh")
    assert "****" in conn.client_secret


def test_validate_auth_surface(service: AdminAuthSurfaceService) -> None:
    # 1. Valid configuration
    valid_dto = AdminAuthSurfaceConfigDto(
        login_methods=LoginMethodSettingsDto(password_enabled=True),
        oauth_connections=[],
    )
    res_valid = service.validate_auth_surface(valid_dto)
    assert res_valid.is_valid is True
    assert res_valid.active_login_method_count == 1
    assert len(res_valid.errors) == 0

    # 2. Invalid configuration - lockout scenario
    invalid_dto = AdminAuthSurfaceConfigDto(
        login_methods=LoginMethodSettingsDto(
            password_enabled=False,
            email_code_enabled=False,
        ),
        oauth_connections=[],
    )
    res_invalid = service.validate_auth_surface(invalid_dto)
    assert res_invalid.is_valid is False
    assert res_invalid.active_login_method_count == 0
    assert any("Deadlock condition" in err for err in res_invalid.errors)


def test_update_auth_surface_preserves_masked_secrets(
    service: AdminAuthSurfaceService,
) -> None:
    masked_dto = service.get_auth_surface(masked=True)
    masked_secret = masked_dto.oauth_connections[0].client_secret
    assert "****" in masked_secret

    # Update with the masked secret preserving flag
    update_req = UpdateAuthSurfaceRequest(
        config=AdminAuthSurfaceConfigDto(
            login_methods=LoginMethodSettingsDto(
                password_enabled=True,
                email_code_enabled=True,
            ),
            oauth_connections=[
                OAuthConnectionDto(
                    id="github_oauth",
                    provider="github",
                    name="GitHub Renamed",
                    client_id="gh_client_123",
                    client_secret=masked_secret,  # Sending back masked secret
                    authorize_url="https://github.com/login/oauth/authorize",
                    token_url="https://github.com/login/oauth/access_token",
                    enabled=True,
                )
            ],
            allow_public_registration=False,
            mfa_enforced=True,
        ),
        preserve_masked_secrets=True,
    )

    update_resp = service.update_auth_surface(update_req)
    assert update_resp.validation.is_valid is True
    assert update_resp.config.mfa_enforced is True
    assert update_resp.config.login_methods.email_code_enabled is True

    # Underlying unmasked secret must be preserved
    unmasked = service.get_auth_surface(masked=False)
    assert unmasked.oauth_connections[0].client_secret == "gh_secret_super_secret_999"


def test_update_auth_surface_lockout_rejected(service: AdminAuthSurfaceService) -> None:
    lockout_req = UpdateAuthSurfaceRequest(
        config=AdminAuthSurfaceConfigDto(
            login_methods=LoginMethodSettingsDto(
                password_enabled=False,
                email_code_enabled=False,
            ),
            oauth_connections=[],
        ),
    )
    with pytest.raises(ValueError, match="Deadlock condition"):
        service.update_auth_surface(lockout_req)


def test_get_admin_auth_surface_service_singleton() -> None:
    svc1 = get_admin_auth_surface_service()
    svc2 = get_admin_auth_surface_service()
    assert svc1 is svc2
