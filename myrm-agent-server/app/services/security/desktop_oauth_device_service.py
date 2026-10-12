"""Service layer for Desktop OAuth Browser Flow & RFC 8628 Device Code Grant.

[INPUT]
- DesktopOAuthInitRequest, DeviceCodeInitRequest, DeviceCodeAuthorizeRequest,
  DeviceCodePollRequest, TokenRotationRequest DTOs.

[OUTPUT]
- DesktopOAuthInitResponseDto, DeviceCodeSessionDto, DeviceCodePollResponseDto,
  TokenRotationResponseDto.

[POS]
- Server service coordinating PKCE challenge generation, RFC 8628 session management,
  and silent background token rotation.
"""

from __future__ import annotations

import time

from myrm_agent_harness.core.security.desktop_oauth_device.device_code_engine import (
    DeviceCodeEngine,
)
from myrm_agent_harness.core.security.desktop_oauth_device.pkce import (
    build_authorization_url,
    generate_pkce_challenge,
)
from myrm_agent_harness.core.security.desktop_oauth_device.token_rotator import (
    SilentTokenRotator,
)
from myrm_agent_harness.core.security.desktop_oauth_device.types import (
    OAuthTokenGrant,
)

from app.schemas.desktop_oauth_device import (
    DesktopOAuthInitRequest,
    DesktopOAuthInitResponseDto,
    DeviceCodeAuthorizeRequest,
    DeviceCodeInitRequest,
    DeviceCodePollRequest,
    DeviceCodePollResponseDto,
    DeviceCodeSessionDto,
    TokenRotationRequest,
    TokenRotationResponseDto,
)


class DesktopOAuthDeviceService:
    """Manages desktop browser PKCE handshakes, RFC 8628 device flows, and token lifecycles."""

    def __init__(
        self,
        device_engine: DeviceCodeEngine | None = None,
        token_rotator: SilentTokenRotator | None = None,
    ) -> None:
        self._device_engine = device_engine or DeviceCodeEngine()
        self._token_rotator = token_rotator or SilentTokenRotator()

    def init_desktop_oauth(
        self, request: DesktopOAuthInitRequest
    ) -> DesktopOAuthInitResponseDto:
        """Generate PKCE challenge and authorization URL for desktop browser login."""
        redirect_uri = f"http://127.0.0.1:{request.loopback_port}/callback"
        challenge = generate_pkce_challenge()
        auth_url = build_authorization_url(
            base_auth_url=request.base_auth_url,
            client_id=request.client_id,
            redirect_uri=redirect_uri,
            challenge=challenge,
            scopes=request.scopes,
        )

        return DesktopOAuthInitResponseDto(
            provider=request.provider,
            authorization_url=auth_url,
            state=challenge.state,
            code_verifier=challenge.code_verifier,
            redirect_uri=redirect_uri,
        )

    def initiate_device_flow(
        self, request: DeviceCodeInitRequest
    ) -> DeviceCodeSessionDto:
        """Create a new RFC 8628 device authorization session."""
        session = self._device_engine.initiate_session(
            verification_uri=request.verification_uri,
            client_id=request.client_id,
            scope=request.scope,
            expires_in=request.expires_in,
            interval=request.interval,
        )

        return DeviceCodeSessionDto(
            device_code=session.device_code,
            user_code=session.user_code,
            verification_uri=session.verification_uri,
            verification_uri_complete=session.verification_uri_complete,
            expires_in=session.expires_in,
            interval=session.interval,
            status=session.status.value,
        )

    def authorize_device_code(
        self, request: DeviceCodeAuthorizeRequest
    ) -> tuple[bool, str]:
        """Authorize a device session using verified user code."""
        grant = OAuthTokenGrant(
            access_token=request.access_token,
            refresh_token=request.refresh_token,
            expires_in=request.expires_in,
            created_at=time.time(),
        )
        return self._device_engine.authorize_user_code(
            user_code=request.user_code, token_grant=grant
        )

    def poll_device_code(
        self, request: DeviceCodePollRequest
    ) -> DeviceCodePollResponseDto:
        """Poll the device authorization status."""
        status, token, msg = self._device_engine.poll_session(
            device_code=request.device_code,
            enforce_interval=request.enforce_interval,
        )

        access_token = token.access_token if token else None
        refresh_token = token.refresh_token if token else None

        return DeviceCodePollResponseDto(
            status=status.value,
            access_token=access_token,
            refresh_token=refresh_token,
            message=msg,
        )

    def register_token_grant(self, provider: str, grant: OAuthTokenGrant) -> None:
        """Register active grant in token rotator."""
        self._token_rotator.register_grant(provider, grant)

    def rotate_token(
        self, request: TokenRotationRequest
    ) -> TokenRotationResponseDto:
        """Inspect and perform silent token renewal."""
        def _mock_refresh(prov: str, rft: str) -> OAuthTokenGrant | None:
            new_token_val = (
                request.simulate_new_access_token
                or f"act_rotated_{int(time.time())}"
            )
            return OAuthTokenGrant(
                access_token=new_token_val,
                refresh_token=f"{rft}_rotated",
                expires_in=3600,
                created_at=time.time(),
            )

        handler = _mock_refresh if request.simulate_new_access_token is not None else None

        result = self._token_rotator.ensure_active_token(
            provider=request.provider,
            refresh_handler=handler,
            buffer_seconds=request.buffer_seconds,
        )

        access_token = result.token.access_token if result.token else None

        return TokenRotationResponseDto(
            provider=request.provider,
            status=result.status.value,
            rotated=result.rotated,
            access_token=access_token,
            message=result.message,
        )


_default_service: DesktopOAuthDeviceService | None = None


def get_desktop_oauth_device_service() -> DesktopOAuthDeviceService:
    """Singleton provider for DesktopOAuthDeviceService."""
    global _default_service
    if _default_service is None:
        _default_service = DesktopOAuthDeviceService()
    return _default_service
