"""API router for Desktop OAuth Browser Flow & RFC 8628 Device Code Grant.

[INPUT]
- DesktopOAuthInitRequest, DeviceCodeInitRequest, DeviceCodeAuthorizeRequest,
  DeviceCodePollRequest, TokenRotationRequest payloads.

[OUTPUT]
- JSON responses for PKCE initiation, RFC 8628 session management, and silent token rotation.

[POS]
- Security router mounted under /security/desktop-oauth-device.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

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
from app.services.security.desktop_oauth_device_service import (
    DesktopOAuthDeviceService,
    get_desktop_oauth_device_service,
)

router = APIRouter(prefix="/desktop-oauth-device", tags=["desktop-oauth-device"])


@router.post("/init-desktop-oauth", response_model=DesktopOAuthInitResponseDto)
async def init_desktop_oauth(
    request: DesktopOAuthInitRequest,
    service: DesktopOAuthDeviceService = Depends(get_desktop_oauth_device_service),
) -> DesktopOAuthInitResponseDto:
    """Initialize PKCE desktop browser OAuth flow and return authorization URL."""
    return service.init_desktop_oauth(request)


@router.post("/device/initiate", response_model=DeviceCodeSessionDto)
async def initiate_device_flow(
    request: DeviceCodeInitRequest,
    service: DesktopOAuthDeviceService = Depends(get_desktop_oauth_device_service),
) -> DeviceCodeSessionDto:
    """Initiate RFC 8628 device authorization session for headless / sandbox environments."""
    return service.initiate_device_flow(request)


@router.post("/device/authorize")
async def authorize_device_code(
    request: DeviceCodeAuthorizeRequest,
    service: DesktopOAuthDeviceService = Depends(get_desktop_oauth_device_service),
) -> dict[str, str | bool]:
    """Approve and authorize a user code with granted access token."""
    success, message = service.authorize_device_code(request)
    if not success:
        raise HTTPException(status_code=400, detail=message)
    return {"success": True, "message": message}


@router.post("/device/poll", response_model=DeviceCodePollResponseDto)
async def poll_device_code(
    request: DeviceCodePollRequest,
    service: DesktopOAuthDeviceService = Depends(get_desktop_oauth_device_service),
) -> DeviceCodePollResponseDto:
    """Poll RFC 8628 device authorization status."""
    return service.poll_device_code(request)


@router.post("/token/rotate", response_model=TokenRotationResponseDto)
async def rotate_token(
    request: TokenRotationRequest,
    service: DesktopOAuthDeviceService = Depends(get_desktop_oauth_device_service),
) -> TokenRotationResponseDto:
    """Inspect and perform silent background token renewal."""
    return service.rotate_token(request)
