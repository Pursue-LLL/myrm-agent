"""
[INPUT]
- app.services.webui.auth_service::webui_auth_service (POS: WebUI browser auth orchestration)

[OUTPUT]
- FastAPI routes under /webui/auth/*

[POS]
WebUI 浏览器认证 HTTP 入口（setup/login/status/logout/token-exchange）。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.services.webui.admin_store import admin_is_configured
from app.services.webui.auth_service import WebuiAuthStatus, webui_auth_service
from app.services.webui.protection_store import is_password_protection_enabled

router = APIRouter(tags=["webui-auth"])


class AuthStatusResponse(BaseModel):
    is_setup_done: bool
    is_authenticated: bool
    user_id: str
    username: str
    role: str


class SetupRequest(BaseModel):
    temp_token: str = Field(min_length=1)
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class TokenExchangeRequest(BaseModel):
    temp_token: str = Field(min_length=1)


class ProtectionConfigResponse(BaseModel):
    require_password: bool
    admin_configured: bool


class ProtectionUpdateRequest(BaseModel):
    require_password: bool


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=8, max_length=256)


class DisableProtectionRequest(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class SetupTokenResponse(BaseModel):
    temp_token: str
    setup_path: str


def _to_response(status_payload: WebuiAuthStatus) -> dict[str, object]:
    return {
        "is_setup_done": status_payload.is_setup_done,
        "is_authenticated": status_payload.is_authenticated,
        "user_id": status_payload.user_id,
        "username": status_payload.username,
        "role": status_payload.role,
    }


def _authenticated_payload(username: str) -> dict[str, object]:
    return {
        "is_setup_done": True,
        "is_authenticated": True,
        "user_id": "local-user",
        "username": username,
        "role": "admin",
    }


def _json_with_session(username: str, request: Request) -> JSONResponse:
    response = JSONResponse(content=_authenticated_payload(username))
    webui_auth_service.attach_session_cookie(response, username, request=request)
    return response


@router.get("/auth/status")
async def get_auth_status(request: Request) -> AuthStatusResponse:
    payload = webui_auth_service.resolve_status(request)
    return AuthStatusResponse(**_to_response(payload))


@router.post("/auth/setup")
async def setup_admin(request: Request, body: SetupRequest) -> JSONResponse:
    try:
        webui_auth_service.setup_admin(
            request,
            temp_token=body.temp_token,
            username=body.username,
            password=body.password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return _json_with_session(body.username.strip(), request)


@router.post("/auth/login")
async def login(request: Request, body: LoginRequest) -> JSONResponse:
    try:
        session_username = webui_auth_service.login(
            request,
            username=body.username,
            password=body.password,
        )
    except PermissionError as exc:
        retry_after = 60
        message = str(exc)
        if message.endswith("seconds."):
            tail = message.rsplit(" ", 2)[-2]
            if tail.isdigit():
                retry_after = int(tail)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=message,
            headers={"Retry-After": str(retry_after)},
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return _json_with_session(session_username, request)


@router.post("/auth/token-exchange")
async def token_exchange(request: Request, body: TokenExchangeRequest) -> JSONResponse:
    try:
        session_username = webui_auth_service.exchange_temp_token(request, temp_token=body.temp_token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return _json_with_session(session_username, request)


@router.post("/auth/logout")
async def logout() -> JSONResponse:
    response = JSONResponse(content={"ok": True})
    webui_auth_service.clear_session_cookie(response)
    return response


@router.get("/auth/protection", response_model=ProtectionConfigResponse)
async def get_protection_config() -> ProtectionConfigResponse:
    return ProtectionConfigResponse(
        require_password=is_password_protection_enabled(),
        admin_configured=admin_is_configured(),
    )


@router.put("/auth/protection", response_model=ProtectionConfigResponse)
async def update_protection_config(body: ProtectionUpdateRequest) -> ProtectionConfigResponse:
    webui_auth_service.update_protection_enabled(enabled=body.require_password)
    return ProtectionConfigResponse(
        require_password=is_password_protection_enabled(),
        admin_configured=admin_is_configured(),
    )


@router.post("/auth/change-password")
async def change_password(request: Request, body: ChangePasswordRequest) -> JSONResponse:
    try:
        username = webui_auth_service.change_password(
            request,
            current_password=body.current_password,
            new_password=body.new_password,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return _json_with_session(username, request)


@router.post("/auth/disable-protection")
async def disable_protection(request: Request, body: DisableProtectionRequest) -> dict[str, bool]:
    try:
        webui_auth_service.disable_password_protection(request, password=body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    return {"ok": True}


@router.post("/auth/generate-setup-token", response_model=SetupTokenResponse)
async def generate_setup_token(request: Request) -> SetupTokenResponse:
    try:
        token = webui_auth_service.generate_setup_token(request)
    except PermissionError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    return SetupTokenResponse(temp_token=token, setup_path=f"/auth/setup?token={token}")
