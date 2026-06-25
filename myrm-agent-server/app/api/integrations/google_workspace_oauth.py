"""Google Workspace OAuth 2.0 + PKCE authorization flow.

[INPUT]
- app.api.integrations.google_workspace_oauth_flow (POS: PKCE state, scopes, redirect URI, skill enablement)
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)
- myrm_agent_harness.toolkits.mcp.oauth::generate_pkce_pair (POS: PKCE pair for /start)

[OUTPUT]
Google Workspace OAuth API under /integrations/google-workspace/oauth

[POS]
HTTP routes for Calendar/Gmail/Drive OAuth connect. Delegates flow helpers to
google_workspace_oauth_flow; persists issuer google_workspace into UserConfig
oauthCredentials (tokens only; client_id/secret stay in server settings).
"""

from __future__ import annotations

import html
import logging
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from myrm_agent_harness.toolkits.mcp.oauth import generate_pkce_pair
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.integrations import google_workspace_oauth_flow as flow
from app.core.infra.limiter import limiter
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.services.agent.oauth_refresher import GOOGLE_WORKSPACE_ISSUER
from app.services.integrations.oauth_store import (
    delete_oauth_credential,
    decrypt_oauth_credentials,
    google_workspace_write_enabled,
    is_oauth_issuer_connected,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Re-exported for tests and backward-compatible patch paths.
_pending_auth = flow.pending_auth
_successful_auth = flow.successful_auth
_successful_auth_meta = flow.successful_auth_meta


@router.get("/config")
async def get_google_workspace_oauth_config(request: Request) -> JSONResponse:
    """Return whether server-side Google OAuth client credentials are configured."""
    base = await flow.resolve_oauth_base_url(request)
    return success_response(
        data={
            "configured": flow.oauth_configured(),
            "issuer": GOOGLE_WORKSPACE_ISSUER,
            "callback_path": flow.callback_path(),
            "redirect_uri": flow.build_redirect_uri(base),
        }
    )


@router.post("/start")
@limiter.limit("10/minute")
async def start_google_workspace_oauth(request: Request) -> JSONResponse:
    """Start Google Workspace OAuth authorization flow."""
    flow.require_oauth_configured()
    flow.evict_expired_pending()

    tier = "readonly"
    try:
        payload = await request.json()
        if isinstance(payload, dict):
            tier = flow.GoogleWorkspaceOAuthStartBody.model_validate(payload).tier
    except Exception:
        tier = "readonly"

    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    redirect_uri = flow.build_redirect_uri(await flow.resolve_oauth_base_url(request))
    scope = flow.scopes_for_tier(tier)

    _pending_auth[state] = {
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
        "created_at": str(time.time()),
        "tier": tier,
    }

    auth_url = flow.build_google_auth_url(
        state=state,
        code_challenge=code_challenge,
        redirect_uri=redirect_uri,
        scope=scope,
    )
    logger.info("Google Workspace OAuth flow started (tier=%s)", tier)
    return success_response(data={"authorization_url": auth_url, "state": state, "tier": tier})


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
    if time.time() - created_at > flow.EXPIRY_SECONDS:
        return HTMLResponse(
            content="<html><body><h1>OAuth authorization timed out (10 minutes). Please restart.</h1></body></html>",
            status_code=400,
        )

    token_data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "client_id": flow.client_id(),
        "client_secret": flow.client_secret(),
        "code_verifier": pending["code_verifier"],
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(flow.GOOGLE_TOKEN_ENDPOINT, data=token_data)

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
        scope = str(result.get("scope") or flow.GOOGLE_WORKSPACE_SCOPES)
        user_id = await flow.fetch_google_user_id(str(access_token))

        await upsert_oauth_credential(
            db,
            GOOGLE_WORKSPACE_ISSUER,
            {
                "token": str(access_token),
                "refresh_token": refresh_token or "",
                "token_url": flow.GOOGLE_TOKEN_ENDPOINT,
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
        return HTMLResponse(content=flow.SUCCESS_HTML)

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
    if not await is_oauth_issuer_connected(db, GOOGLE_WORKSPACE_ISSUER):
        return success_response(
            data={
                "issuer": GOOGLE_WORKSPACE_ISSUER,
                "connected": False,
                "write_enabled": False,
                "user_id": None,
                "scope": None,
                "expires_at": None,
            }
        )

    row = await load_oauth_credentials_row(db)
    if row is None:
        raise HTTPException(status_code=503, detail="Google Workspace OAuth state inconsistent")

    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
    cred_val = credentials.get(GOOGLE_WORKSPACE_ISSUER)
    if not isinstance(cred_val, dict):
        return success_response(
            data={
                "issuer": GOOGLE_WORKSPACE_ISSUER,
                "connected": False,
                "write_enabled": False,
                "user_id": None,
                "scope": None,
                "expires_at": None,
            }
        )

    scope = cred_val.get("scope")
    return success_response(
        data={
            "issuer": GOOGLE_WORKSPACE_ISSUER,
            "connected": True,
            "write_enabled": google_workspace_write_enabled(scope),
            "user_id": cred_val.get("user_id"),
            "scope": scope,
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

# Backward-compatible alias for tests patching skill enablement.
_maybe_enable_google_workspace_skill = flow.maybe_enable_google_workspace_skill
