"""Google Workspace OAuth flow helpers (PKCE state, scopes, redirect resolution).

[INPUT]
- app.config.settings::settings (POS: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)
- app.core.infra.ingress::get_public_ingress_base_url (POS: public OAuth redirect base)
- app.core.skills.store.service::skills_service (POS: prebuilt skill enablement)

[OUTPUT]
PKCE pending/success state, scope tiers, redirect URI builders, Google userinfo fetch

[POS]
Helper module extracted from google_workspace_oauth.py to keep route handlers under
the 400-line CI budget without changing OAuth behavior.
"""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.skills.oauth_availability import GOOGLE_WORKSPACE_SKILL_ID
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER

logger = logging.getLogger(__name__)

GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_WORKSPACE_READONLY_SCOPES: tuple[str, ...] = (
    "openid",
    "email",
    "profile",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
)

GOOGLE_WORKSPACE_WRITE_SCOPES: tuple[str, ...] = (
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar.events",
)

GOOGLE_WORKSPACE_SCOPES = " ".join(GOOGLE_WORKSPACE_READONLY_SCOPES)

_MAX_PENDING = 50
EXPIRY_SECONDS = 600

pending_auth: dict[str, dict[str, str]] = {}
successful_auth: dict[str, float] = {}
successful_auth_meta: dict[str, dict[str, bool]] = {}

SUCCESS_HTML = """
<html>
<head><style>body{font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background:#f9fafb;margin:0;color:#111827;}</style></head>
<body>
    <div style="text-align:center;padding:40px;background:white;border-radius:12px;box-shadow:0 4px 6px -1px rgba(0,0,0,0.1);">
        <svg style="width:64px;height:64px;color:#10b981;margin:0 auto 16px;" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
        <h1 style="margin:0 0 8px;font-size:24px;font-weight:600;">Authorization Successful</h1>
        <p style="margin:0;color:#6b7280;">You can safely close this tab and return to the application.</p>
        <script>setTimeout(() => window.close(), 3000);</script>
    </div>
</body>
</html>
"""


class GoogleWorkspaceOAuthStartBody(BaseModel):
    tier: str = Field(default="readonly", pattern="^(readonly|write)$")


def client_id() -> str:
    return settings.google_client_id.strip()


def client_secret() -> str:
    return settings.google_client_secret.get_secret_value().strip()


def oauth_configured() -> bool:
    return bool(client_id() and client_secret())


def require_oauth_configured() -> None:
    if not oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )


def callback_path() -> str:
    return f"{settings.api_prefix}/integrations/google-workspace/oauth/callback"


async def resolve_oauth_base_url(request: Request) -> str:
    """Public base URL for OAuth redirect_uri (ingress resolver, then request base)."""
    ingress = (await get_public_ingress_base_url()).strip().rstrip("/")
    if ingress:
        return ingress
    return str(request.base_url).rstrip("/")


def build_redirect_uri(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{callback_path()}"


def scopes_for_tier(tier: str) -> str:
    scopes = list(GOOGLE_WORKSPACE_READONLY_SCOPES)
    if tier == "write":
        scopes.extend(GOOGLE_WORKSPACE_WRITE_SCOPES)
    return " ".join(scopes)


def evict_expired_pending() -> None:
    now = time.time()
    if len(pending_auth) > _MAX_PENDING:
        expired = [k for k, v in pending_auth.items() if now - float(v.get("created_at", "0")) > EXPIRY_SECONDS]
        for k in expired:
            del pending_auth[k]

    if len(successful_auth) > _MAX_PENDING:
        expired_success = [k for k, v in successful_auth.items() if now - v > EXPIRY_SECONDS]
        for k in expired_success:
            del successful_auth[k]


def build_google_auth_url(*, state: str, code_challenge: str, redirect_uri: str, scope: str) -> str:
    params = {
        "response_type": "code",
        "client_id": client_id(),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": scope,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


async def fetch_google_user_id(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            GOOGLE_USERINFO_ENDPOINT,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            logger.warning("Google userinfo failed: %d %s", resp.status_code, resp.text[:200])
            return ""
        data = resp.json()
        return str(data.get("email") or data.get("id") or "")


async def maybe_enable_google_workspace_skill() -> tuple[bool, bool]:
    """Enable google-workspace prebuilt skill unless user explicitly disabled it."""
    from app.core.skills.store.service import skills_service

    config = await skills_service.user_config.get_config()
    if GOOGLE_WORKSPACE_SKILL_ID in config.disabled_prebuilt_ids:
        logger.info(
            "Google Workspace OAuth connected but skill '%s' remains disabled by user choice",
            GOOGLE_WORKSPACE_SKILL_ID,
        )
        return False, True

    if GOOGLE_WORKSPACE_SKILL_ID not in config.enabled_prebuilt_ids:
        await skills_service.user_config.enable_prebuilt_skill(GOOGLE_WORKSPACE_SKILL_ID)
        return True, False

    return True, False


__all__ = [
    "GOOGLE_AUTH_ENDPOINT",
    "GOOGLE_TOKEN_ENDPOINT",
    "GOOGLE_USERINFO_ENDPOINT",
    "GOOGLE_WORKSPACE_ISSUER",
    "GOOGLE_WORKSPACE_SCOPES",
    "GoogleWorkspaceOAuthStartBody",
    "SUCCESS_HTML",
    "build_google_auth_url",
    "build_redirect_uri",
    "callback_path",
    "client_id",
    "client_secret",
    "EXPIRY_SECONDS",
    "evict_expired_pending",
    "fetch_google_user_id",
    "maybe_enable_google_workspace_skill",
    "oauth_configured",
    "pending_auth",
    "require_oauth_configured",
    "resolve_oauth_base_url",
    "successful_auth",
    "successful_auth_meta",
]
