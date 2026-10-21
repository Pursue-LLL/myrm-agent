"""
[INPUT]
- app.config.deploy_mode (POS: local / remote / sandbox flags)
- app.services.webui.admin_store (POS: admin credential presence)
- app.services.webui.protection_store (POS: require_password toggle)
- app.services.webui.session (POS: session cookie parsing)

[OUTPUT]
- local_api_requires_session: whether API must see a valid WebUI session
- resolve_webui_session_username: parse session user from Cookie header

[POS]
WebUI 访问策略（供 identity 与 auth_service 共用，避免循环依赖）。
"""

from __future__ import annotations

from collections.abc import Mapping

from app.config.deploy_mode import DeployMode, get_deploy_mode, is_local_mode, is_webui_remote_mode
from app.services.webui.admin_store import admin_is_configured
from app.services.webui.protection_store import is_password_protection_enabled
from app.services.webui.session import SESSION_COOKIE_NAME, parse_session_value


def local_api_requires_session() -> bool:
    if get_deploy_mode() == DeployMode.SANDBOX or not is_local_mode():
        return False
    if not admin_is_configured():
        return is_webui_remote_mode()
    return is_password_protection_enabled()


def resolve_webui_session_username(
    headers: Mapping[str, str],
    *,
    max_idle_seconds: int | None = None,
) -> str | None:
    cookie_header = ""
    for key, value in headers.items():
        if key.lower() == "cookie":
            cookie_header = value
            break
    if not cookie_header:
        return None
    prefix = f"{SESSION_COOKIE_NAME}="
    for part in cookie_header.split(";"):
        chunk = part.strip()
        if chunk.startswith(prefix):
            return parse_session_value(chunk[len(prefix) :], max_idle_seconds=max_idle_seconds)
    return None


__all__ = ["local_api_requires_session", "resolve_webui_session_username"]
