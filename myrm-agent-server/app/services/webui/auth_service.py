"""
[INPUT]
- app.services.webui.admin_store (POS: admin credential persistence)
- app.services.webui.temp_token (POS: setup token issuance)
- app.services.webui.session (POS: signed session cookies)
- app.remote_access.pairing (POS: mobile pair token HMAC signing)
- app.config.deploy_mode (POS: local vs remote WebUI flags)

[OUTPUT]
- WebuiAuthService: resolve_status, setup_admin, login, exchange_temp_token
- webui_auth_service: process singleton

[POS]
WebUI 浏览器会话认证编排（本地/远程单机，非控制平面 Sandbox 登录）。
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass

from fastapi import Request, Response

from app.config.deploy_mode import DeployMode, get_deploy_mode, is_webui_remote_mode
from app.core.security.auth.identity import is_loopback_ip
from app.remote_access.pairing import rotate_pairing_key
from app.services.webui.access_policy import local_api_requires_session
from app.services.webui.admin_store import admin_is_configured, load_admin, save_admin
from app.services.webui.passwords import hash_password, verify_password
from app.services.webui.protection_store import (
    set_password_protection_enabled,
)
from app.services.webui.session import (
    SESSION_COOKIE_NAME,
    SESSION_TTL_SECONDS,
    create_session_value,
    parse_session_value,
    rotate_session_signing_key,
)
from app.services.webui.temp_token import temp_token_service

_LOCAL_USER_ID = "local-user"
_MAX_FAILED_ATTEMPTS = 5
_LOCKOUT_SECONDS = 60


@dataclass(frozen=True, slots=True)
class WebuiAuthStatus:
    is_setup_done: bool
    is_authenticated: bool
    user_id: str
    username: str
    role: str


class WebuiAuthService:
    def __init__(self) -> None:
        self._failed_attempts: dict[str, list[float]] = defaultdict(list)

    def _client_key(self, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        return client_ip

    def _is_rate_limited(self, request: Request) -> int | None:
        key = self._client_key(request)
        now = time.time()
        attempts = [ts for ts in self._failed_attempts[key] if now - ts < _LOCKOUT_SECONDS]
        self._failed_attempts[key] = attempts
        if len(attempts) >= _MAX_FAILED_ATTEMPTS:
            oldest = min(attempts)
            retry_after = max(1, int(_LOCKOUT_SECONDS - (now - oldest)))
            return retry_after
        return None

    def _record_failed_attempt(self, request: Request) -> None:
        self._failed_attempts[self._client_key(request)].append(time.time())

    def _clear_failed_attempts(self, request: Request) -> None:
        self._failed_attempts.pop(self._client_key(request), None)

    def _session_username(self, request: Request) -> str | None:
        cookie = request.cookies.get(SESSION_COOKIE_NAME)
        return parse_session_value(cookie)

    def _password_required(self) -> bool:
        return local_api_requires_session()

    def resolve_status(self, request: Request) -> WebuiAuthStatus:
        if get_deploy_mode() == DeployMode.SANDBOX:
            return WebuiAuthStatus(
                is_setup_done=True,
                is_authenticated=True,
                user_id=_LOCAL_USER_ID,
                username="Local User",
                role="admin",
            )

        configured = admin_is_configured()
        remote = is_webui_remote_mode()
        client_ip = request.client.host if request.client else ""
        loopback = is_loopback_ip(client_ip)

        if not configured:
            if remote:
                return WebuiAuthStatus(
                    is_setup_done=False,
                    is_authenticated=False,
                    user_id=_LOCAL_USER_ID,
                    username="admin",
                    role="admin",
                )
            return WebuiAuthStatus(
                is_setup_done=True,
                is_authenticated=True,
                user_id=_LOCAL_USER_ID,
                username="Local User",
                role="admin",
            )

        admin = load_admin()
        display_name = admin.username if admin else "admin"
        session_user = self._session_username(request)
        if session_user:
            return WebuiAuthStatus(
                is_setup_done=True,
                is_authenticated=True,
                user_id=_LOCAL_USER_ID,
                username=session_user,
                role="admin",
            )
        if loopback and (not self._password_required() or not remote):
            return WebuiAuthStatus(
                is_setup_done=True,
                is_authenticated=True,
                user_id=_LOCAL_USER_ID,
                username=display_name,
                role="admin",
            )
        return WebuiAuthStatus(
            is_setup_done=True,
            is_authenticated=False,
            user_id=_LOCAL_USER_ID,
            username=display_name,
            role="admin",
        )

    @staticmethod
    def _request_uses_https(request: Request) -> bool:
        if request.url.scheme == "https":
            return True
        forwarded = request.headers.get("x-forwarded-proto", "").split(",")[0].strip().lower()
        return forwarded == "https"

    def attach_session_cookie(self, response: Response, username: str, *, request: Request | None = None) -> None:
        value = create_session_value(username)
        secure = self._request_uses_https(request) if request is not None else False
        response.set_cookie(
            key=SESSION_COOKIE_NAME,
            value=value,
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            samesite="lax",
            secure=secure,
            path="/",
        )

    def invalidate_all_sessions(self) -> None:
        rotate_session_signing_key()
        rotate_pairing_key()

    def clear_session_cookie(self, response: Response) -> None:
        response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")

    def setup_admin(
        self,
        request: Request,
        *,
        temp_token: str,
        username: str,
        password: str,
    ) -> None:
        if not temp_token_service.consume_token(temp_token):
            raise ValueError("Invalid or expired setup token")
        if admin_is_configured():
            raise ValueError("Admin account is already configured")
        cleaned = username.strip()
        if not cleaned:
            raise ValueError("Username is required")
        if len(password) < 8:
            raise ValueError("Password must be at least 8 characters")
        save_admin(cleaned, hash_password(password))

    def login(
        self,
        request: Request,
        *,
        username: str,
        password: str,
    ) -> str:
        retry_after = self._is_rate_limited(request)
        if retry_after is not None:
            raise PermissionError(f"Too many failed attempts. Retry after {retry_after} seconds.")

        if not self._password_required() and not admin_is_configured():
            self._clear_failed_attempts(request)
            return "Local User"

        admin = load_admin()
        if admin is None:
            raise ValueError("Admin account is not configured")

        if username.strip() != admin.username or not verify_password(password, admin.password_hash):
            self._record_failed_attempt(request)
            raise ValueError("Invalid username or password")

        self._clear_failed_attempts(request)
        return admin.username

    def exchange_temp_token(self, request: Request, *, temp_token: str) -> str:
        if not admin_is_configured():
            raise ValueError("Admin account is not configured")
        if not temp_token_service.consume_token(temp_token):
            raise ValueError("Invalid or expired token")
        admin = load_admin()
        if admin is None:
            raise ValueError("Admin account is not configured")
        self._clear_failed_attempts(request)
        return admin.username

    def change_password(
        self,
        request: Request,
        *,
        current_password: str,
        new_password: str,
    ) -> str:
        admin = load_admin()
        if admin is None:
            raise ValueError("Admin account is not configured")
        if not verify_password(current_password, admin.password_hash):
            raise ValueError("Invalid current password")
        if len(new_password) < 8:
            raise ValueError("Password must be at least 8 characters")
        save_admin(admin.username, hash_password(new_password))
        self.invalidate_all_sessions()
        return admin.username

    def disable_password_protection(self, request: Request, *, password: str) -> None:
        admin = load_admin()
        if admin is None:
            set_password_protection_enabled(False)
            return
        if not verify_password(password, admin.password_hash):
            raise ValueError("Invalid password")
        set_password_protection_enabled(False)

    def update_protection_enabled(self, *, enabled: bool) -> None:
        set_password_protection_enabled(enabled)
        if enabled:
            self.invalidate_all_sessions()

    def generate_setup_token(self, request: Request) -> str:
        if not admin_is_configured():
            client_ip = request.client.host if request.client else ""
            if not is_loopback_ip(client_ip):
                raise PermissionError("Setup token can only be generated from loopback before admin exists")
            return temp_token_service.generate_token()
        status = self.resolve_status(request)
        if not status.is_authenticated:
            raise PermissionError("Authentication required to generate setup token")
        return temp_token_service.generate_token()


webui_auth_service = WebuiAuthService()


__all__ = ["WebuiAuthStatus", "WebuiAuthService", "webui_auth_service"]
