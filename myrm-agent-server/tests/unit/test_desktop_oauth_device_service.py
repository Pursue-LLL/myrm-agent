"""Unit test for DesktopOAuthDeviceService.

[INPUT]
- DesktopOAuthInitRequest, DeviceCodeInitRequest, DeviceCodeAuthorizeRequest,
  DeviceCodePollRequest, TokenRotationRequest.

[OUTPUT]
- Verified behavior of desktop OAuth initialization, device code flows, and token rotation.

[POS]
- Server unit test layer for desktop OAuth and headless device code authentication.
"""

from __future__ import annotations

import time

from myrm_agent_harness.core.security.desktop_oauth_device.types import (
    OAuthTokenGrant,
)

from app.schemas.desktop_oauth_device import (
    DesktopOAuthInitRequest,
    DeviceCodeAuthorizeRequest,
    DeviceCodeInitRequest,
    DeviceCodePollRequest,
    TokenRotationRequest,
)
from app.services.security.desktop_oauth_device_service import (
    DesktopOAuthDeviceService,
)


def test_service_init_desktop_oauth() -> None:
    service = DesktopOAuthDeviceService()
    req = DesktopOAuthInitRequest(
        provider="github",
        client_id="gh-client-xyz",
        base_auth_url="https://github.com/login/oauth/authorize",
        scopes=["read:user", "repo"],
        loopback_port=41920,
    )
    res = service.init_desktop_oauth(req)

    assert res.provider == "github"
    assert res.redirect_uri == "http://127.0.0.1:41920/callback"
    assert "https://github.com/login/oauth/authorize?" in res.authorization_url
    assert "code_challenge=" in res.authorization_url
    assert "code_challenge_method=S256" in res.authorization_url
    assert len(res.code_verifier) > 40
    assert len(res.state) > 10


def test_service_device_flow_lifecycle() -> None:
    service = DesktopOAuthDeviceService()

    # 1. Initiate device flow
    init_req = DeviceCodeInitRequest(
        client_id="myrm-cli",
        verification_uri="https://auth.myrm.dev/device",
        scope="agent:execute",
        expires_in=600,
        interval=5,
    )
    session_dto = service.initiate_device_flow(init_req)
    assert len(session_dto.device_code) > 20
    assert "-" in session_dto.user_code
    assert session_dto.status == "authorization_pending"

    # 2. Poll before user approves
    poll_req = DeviceCodePollRequest(device_code=session_dto.device_code, enforce_interval=False)
    poll_res = service.poll_device_code(poll_req)
    assert poll_res.status == "authorization_pending"
    assert poll_res.access_token is None

    # 3. Approve via user code
    auth_req = DeviceCodeAuthorizeRequest(
        user_code=session_dto.user_code,
        access_token="act_device_grant_token",
        refresh_token="rft_device_grant_token",
        expires_in=7200,
    )
    ok, msg = service.authorize_device_code(auth_req)
    assert ok is True
    assert "successfully authorized" in msg

    # 4. Poll after approval
    poll_after = service.poll_device_code(poll_req)
    assert poll_after.status == "authorized"
    assert poll_after.access_token == "act_device_grant_token"
    assert poll_after.refresh_token == "rft_device_grant_token"


def test_service_token_rotation() -> None:
    service = DesktopOAuthDeviceService()
    provider = "google"

    # Register an expiring token (expires in 30s < 60s buffer)
    now = time.time()
    grant = OAuthTokenGrant(
        access_token="act_google_old",
        refresh_token="rft_google_valid",
        expires_in=30,
        created_at=now,
    )
    service.register_token_grant(provider, grant)

    # Request rotation with simulation
    req = TokenRotationRequest(
        provider=provider,
        buffer_seconds=60.0,
        simulate_new_access_token="act_google_refreshed_999",
    )
    res = service.rotate_token(req)

    assert res.provider == "google"
    assert res.status == "ACTIVE"
    assert res.rotated is True
    assert res.access_token == "act_google_refreshed_999"
