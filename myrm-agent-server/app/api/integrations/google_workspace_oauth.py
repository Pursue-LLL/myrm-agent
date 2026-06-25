"""Google Workspace OAuth 2.0 + PKCE authorization flow.

[INPUT]
- app.config.settings::settings (POS: GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET)
- app.core.infra.ingress::get_public_ingress_base_url (POS: public OAuth redirect base)
- app.core.skills.store.service::skills_service (POS: prebuilt skill enablement)
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)
- myrm_agent_harness.toolkits.mcp.oauth::generate_pkce_pair (POS: PKCE pair generation)

[OUTPUT]
Google Workspace OAuth API under /integrations/google-workspace/oauth

[POS]
Product-layer OAuth connect flow for Calendar/Gmail/Drive. Persists issuer
google_workspace into UserConfig oauthCredentials (token + refresh metadata only;
client_id/secret stay in server settings). Enables prebuilt google-workspace skill.
"""

from __future__ import annotations

import html
import logging
import secrets
import time
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from myrm_agent_harness.toolkits.mcp.oauth import generate_pkce_pair
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.core.infra.ingress import get_public_ingress_base_url
from app.core.infra.limiter import limiter
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.services.integrations.oauth_store import (
    delete_oauth_credential,
    decrypt_oauth_credentials,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter()

GOOGLE_WORKSPACE_ISSUER = "google_workspace"
GOOGLE_WORKSPACE_SKILL_ID = "google-workspace"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_ENDPOINT = "https://www.googleapis.com/oauth2/v2/userinfo"
GOOGLE_WORKSPACE_SCOPES = " ".join(
    [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
    ]
)

_pending_auth: dict[str, dict[str, str]] = {}
_successful_auth: dict[str, float] = {}
_successful_auth_meta: dict[str, dict[str, bool]] = {}
_MAX_PENDING = 50
_EXPIRY_SECONDS = 600

_SUCCESS_HTML = """
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


def _client_id() -> str:
    return settings.google_client_id.strip()


def _client_secret() -> str:
    return settings.google_client_secret.get_secret_value().strip()


def _oauth_configured() -> bool:
    return bool(_client_id() and _client_secret())


def _require_oauth_configured() -> None:
    if not _oauth_configured():
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured. Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET.",
        )


def _callback_path() -> str:
    return f"{settings.api_prefix}/integrations/google-workspace/oauth/callback"


async def _resolve_oauth_base_url(request: Request) -> str:
    """Public base URL for OAuth redirect_uri (ingress resolver, then request base)."""
    ingress = (await get_public_ingress_base_url()).strip().rstrip("/")
    if ingress:
        return ingress
    return str(request.base_url).rstrip("/")


def _build_redirect_uri(base_url: str) -> str:
    return f"{base_url.rstrip('/')}{_callback_path()}"


async def _maybe_enable_google_workspace_skill() -> tuple[bool, bool]:
    """Enable google-workspace prebuilt skill unless user explicitly disabled it.

    Returns:
        (skill_auto_enabled, skill_was_user_disabled)
    """
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


def _evict_expired_pending() -> None:
    now = time.time()
    if len(_pending_auth) > _MAX_PENDING:
        expired = [k for k, v in _pending_auth.items() if now - float(v.get("created_at", "0")) > _EXPIRY_SECONDS]
        for k in expired:
            del _pending_auth[k]

    if len(_successful_auth) > _MAX_PENDING:
        expired_success = [k for k, v in _successful_auth.items() if now - v > _EXPIRY_SECONDS]
        for k in expired_success:
            del _successful_auth[k]


def _build_google_auth_url(*, state: str, code_challenge: str, redirect_uri: str) -> str:
    params = {
        "response_type": "code",
        "client_id": _client_id(),
        "redirect_uri": redirect_uri,
        "state": state,
        "scope": GOOGLE_WORKSPACE_SCOPES,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
    }
    return f"{GOOGLE_AUTH_ENDPOINT}?{urlencode(params)}"


async def _fetch_google_user_id(access_token: str) -> str:
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


@router.get("/config")
async def get_google_workspace_oauth_config(request: Request) -> JSONResponse:
    """Return whether server-side Google OAuth client credentials are configured."""
    base = await _resolve_oauth_base_url(request)
    return success_response(
        data={
            "configured": _oauth_configured(),
            "issuer": GOOGLE_WORKSPACE_ISSUER,
            "callback_path": _callback_path(),
            "redirect_uri": _build_redirect_uri(base),
        }
    )


@router.post("/start")
@limiter.limit("10/minute")
async def start_google_workspace_oauth(request: Request) -> JSONResponse:
    """Start Google Workspace OAuth authorization flow."""
    _require_oauth_configured()
    _evict_expired_pending()

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    redirect_uri = _build_redirect_uri(await _resolve_oauth_base_url(request))

    _pending_auth[state] = {
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "created_at": str(time.time()),
    }

    auth_url = _build_google_auth_url(state=state, code_challenge=code_challenge, redirect_uri=redirect_uri)
    logger.info("Google Workspace OAuth flow started")
    return success_response(data={"authorization_url": auth_url, "state": state})


@router.get("/callback")
@limiter.limit("10/minute")
async def handle_google_workspace_oauth_callback(
    request: Request,
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    """OAuth provider redirect target; exchanges code for tokens and persists credentials."""
    if error:
        safe_msg = html.escape(error_description or error)
        return HTMLResponse(
            content=f"<html><body><h1>Authorization failed</h1><p>{safe_msg}</p></body></html>",
            status_code=400,
        )

    pending = _pending_auth.pop(state, None)
    if not pending:
        return HTMLResponse(
            content="<html><body><h1>Invalid or expired OAuth state. Please restart the authorization flow.</h1></body></html>",
            status_code=400,
        )

    created_at = float(pending.get("created_at", "0"))
    if time.time() - created_at > _EXPIRY_SECONDS:
        return HTMLResponse(
            content="<html><body><h1>OAuth authorization timed out (10 minutes). Please restart.</h1></body></html>",
            status_code=400,
        )

    token_data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "client_id": _client_id(),
        "client_secret": _client_secret(),
        "code_verifier": pending["code_verifier"],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(GOOGLE_TOKEN_ENDPOINT, data=token_data)

        if resp.status_code != 200:
            logger.error("Google OAuth token exchange failed: %d %s", resp.status_code, resp.text[:300])
            return HTMLResponse(
                content=f"<html><body><h1>Token exchange failed (HTTP {resp.status_code}).</h1></body></html>",
                status_code=400,
            )

        result = resp.json()
        access_token = result.get("access_token")
        if not access_token:
            return HTMLResponse(
                content="<html><body><h1>Token exchange succeeded but access_token was missing.</h1></body></html>",
                status_code=400,
            )

        refresh_token = result.get("refresh_token")
        if not refresh_token:
            logger.warning("Google OAuth completed without refresh_token — token refresh will not work")

        expires_in = int(result.get("expires_in", 3600))
        scope = str(result.get("scope") or GOOGLE_WORKSPACE_SCOPES)
        user_id = await _fetch_google_user_id(str(access_token))

        await upsert_oauth_credential(
            db,
            GOOGLE_WORKSPACE_ISSUER,
            {
                "token": str(access_token),
                "refresh_token": refresh_token or "",
                "token_url": GOOGLE_TOKEN_ENDPOINT,
                "user_id": user_id,
                "scope": scope,
                "expires_at": time.time() + expires_in,
            },
        )

        skill_auto_enabled, skill_was_user_disabled = await _maybe_enable_google_workspace_skill()

        _successful_auth[state] = time.time()
        _successful_auth_meta[state] = {
            "skill_auto_enabled": skill_auto_enabled,
            "skill_was_user_disabled": skill_was_user_disabled,
        }
        logger.info(
            "Google Workspace OAuth completed for user '%s' (skill_auto_enabled=%s)",
            user_id or "(unknown)",
            skill_auto_enabled,
        )
        return HTMLResponse(content=_SUCCESS_HTML)

    except httpx.HTTPError as exc:
        logger.error("Google OAuth token exchange network error: %s", exc)
        safe_exc = html.escape(str(exc))
        return HTMLResponse(
            content=f"<html><body><h1>Network error during token exchange</h1><p>{safe_exc}</p></body></html>",
            status_code=500,
        )


@router.get("/status/{state}")
async def check_google_workspace_oauth_state_status(state: str) -> JSONResponse:
    """Check if a specific OAuth state has successfully completed."""
    if state in _successful_auth:
        meta = _successful_auth_meta.get(state, {})
        return success_response(
            data={
                "status": "success",
                "skill_auto_enabled": bool(meta.get("skill_auto_enabled")),
                "skill_was_user_disabled": bool(meta.get("skill_was_user_disabled")),
            }
        )
    if state in _pending_auth:
        return success_response(data={"status": "pending"})
    return success_response(data={"status": "expired_or_invalid"})


@router.get("/status")
async def get_google_workspace_oauth_status(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Return connection status for Google Workspace OAuth."""
    row = await load_oauth_credentials_row(db)
    if not row:
        return success_response(
            data={
                "issuer": GOOGLE_WORKSPACE_ISSUER,
                "connected": False,
                "user_id": None,
                "scope": None,
                "expires_at": None,
            }
        )

    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
    cred_val = credentials.get(GOOGLE_WORKSPACE_ISSUER)
    if not isinstance(cred_val, dict) or not cred_val.get("token"):
        return success_response(
            data={
                "issuer": GOOGLE_WORKSPACE_ISSUER,
                "connected": False,
                "user_id": None,
                "scope": None,
                "expires_at": None,
            }
        )

    return success_response(
        data={
            "issuer": GOOGLE_WORKSPACE_ISSUER,
            "connected": True,
            "user_id": cred_val.get("user_id"),
            "scope": cred_val.get("scope"),
            "expires_at": cred_val.get("expires_at"),
        }
    )


@router.delete("")
async def disconnect_google_workspace_oauth(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Disconnect Google Workspace OAuth credentials."""
    deleted = await delete_oauth_credential(db, GOOGLE_WORKSPACE_ISSUER)
    if not deleted:
        raise HTTPException(status_code=404, detail="Google Workspace is not connected")
    logger.info("Google Workspace OAuth disconnected")
    return success_response(data={"issuer": GOOGLE_WORKSPACE_ISSUER, "connected": False})
