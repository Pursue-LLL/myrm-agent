"""MCP OAuth authorization API endpoints.

Handles the OAuth 2.0 + PKCE authorization flow for remote MCP servers:
1. POST /start          — Generate auth URL, persist PKCE state
2. GET  /callback       — OAuth provider redirect target; exchanges code for tokens
3. GET  /status/{state} — Check single OAuth flow completion status (polling)
4. GET  /status         — Check OAuth status for all MCP servers
5. DELETE /{name}       — Disconnect (revoke) OAuth for a server

[INPUT]
- app.services.agent.backends.mcp_oauth_store (POS: token persistence)
- myrm_agent_harness.toolkits.mcp.oauth (POS: PKCE + URL generation)

[OUTPUT]
MCP OAuth authorization API endpoints under /integrations/mcp/oauth

[POS]
MCP OAuth 2.0 + PKCE authorization flow API. Backend-driven callback flow:
user triggers auth → backend generates URL → user authorizes in browser →
OAuth provider redirects to backend GET /callback → backend exchanges code
for token → frontend polls GET /status/{state} to detect completion.
"""

from __future__ import annotations

import logging
import secrets
import time

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from myrm_agent_harness.toolkits.mcp.oauth import (
    MCPOAuthConfig,
    MCPOAuthToken,
    build_authorization_url,
    generate_pkce_pair,
)
from pydantic import BaseModel, Field

from app.core.infra.limiter import limiter
from app.core.utils.response_utils import success_response
from app.services.agent.backends.mcp_oauth_store import get_mcp_oauth_token_store

logger = logging.getLogger(__name__)

router = APIRouter()

_pending_auth: dict[str, dict[str, str]] = {}
_successful_auth: dict[str, float] = {}
_MAX_PENDING = 50
_EXPIRY_SECONDS = 600


async def _refresh_connection_pool_auth(server_name: str, token: MCPOAuthToken) -> None:
    """Hot-update auth headers in the MCP connection pool after re-authorization.

    Ensures existing warm sessions pick up the fresh token immediately,
    so the next tool call uses the new credentials without requiring
    a full connection rebuild or page refresh.
    """
    try:
        from myrm_agent_harness.toolkits.mcp.connection_manager import MCPConnectionManager

        if MCPConnectionManager._instance is not None:
            headers = {"Authorization": f"{token.token_type} {token.access_token}"}
            MCPConnectionManager._instance.refresh_server_auth(server_name, headers)
    except Exception:
        logger.debug("Connection pool auth refresh skipped for '%s'", server_name, exc_info=True)


def _evict_expired_pending() -> None:
    """Remove pending auth entries older than 10 minutes (lazy GC)."""
    now = time.time()
    if len(_pending_auth) > _MAX_PENDING:
        expired = [k for k, v in _pending_auth.items() if now - float(v.get("created_at", "0")) > _EXPIRY_SECONDS]
        for k in expired:
            del _pending_auth[k]

    if len(_successful_auth) > _MAX_PENDING:
        expired_success = [k for k, v in _successful_auth.items() if now - v > _EXPIRY_SECONDS]
        for k in expired_success:
            del _successful_auth[k]


class MCPOAuthStartRequest(BaseModel):
    """Request to start an MCP OAuth flow."""

    server_name: str = Field(..., description="MCP server name")
    authorization_endpoint: str = Field(..., description="OAuth authorization endpoint")
    token_endpoint: str = Field(..., description="OAuth token endpoint")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str | None = Field(default=None)
    scope: str | None = Field(default=None)
    redirect_uri: str = Field(..., description="Redirect URI (frontend callback URL)")


class MCPOAuthCallbackRequest(BaseModel):
    """Request to exchange auth code for tokens."""

    server_name: str = Field(..., description="MCP server name")
    code: str = Field(..., description="Authorization code from callback")
    state: str = Field(..., description="State parameter for CSRF verification")
    redirect_uri: str = Field(..., description="Same redirect URI used in /start")


@router.post("/start")
@limiter.limit("10/minute")
async def start_mcp_oauth(body: MCPOAuthStartRequest, request: Request) -> JSONResponse:
    """Start MCP OAuth authorization flow.

    Generates a PKCE code pair, persists the state, and returns the
    authorization URL for the frontend to open in a browser/popup.
    """
    _evict_expired_pending()
    code_verifier, code_challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)

    oauth_config = MCPOAuthConfig(
        authorization_endpoint=body.authorization_endpoint,
        token_endpoint=body.token_endpoint,
        client_id=body.client_id,
        client_secret=body.client_secret,
        scope=body.scope,
    )

    auth_url = build_authorization_url(
        oauth_config=oauth_config,
        state=state,
        code_challenge=code_challenge,
        redirect_uri=body.redirect_uri,
    )

    _pending_auth[state] = {
        "server_name": body.server_name,
        "code_verifier": code_verifier,
        "token_endpoint": body.token_endpoint,
        "client_id": body.client_id,
        "client_secret": body.client_secret or "",
        "redirect_uri": body.redirect_uri,
        "scope": body.scope or "",
        "created_at": str(time.time()),
    }

    logger.info("MCP OAuth flow started for '%s'", body.server_name)
    return success_response(
        data={
            "authorization_url": auth_url,
            "state": state,
        }
    )


@router.get("/callback")
@limiter.limit("10/minute")
async def handle_mcp_oauth_callback(
    request: Request, code: str, state: str, error: str | None = None, error_description: str | None = None
) -> HTMLResponse:
    """Exchange authorization code for OAuth tokens.

    Validates CSRF state, exchanges the code using PKCE code_verifier,
    and persists the resulting tokens (encrypted).
    """
    if error:
        return HTMLResponse(
            content=f"<html><body><h1>Authorization failed</h1><p>{error_description or error}</p></body></html>", status_code=400
        )

    pending = _pending_auth.pop(state, None)
    if not pending:
        return HTMLResponse(
            content="<html><body><h1>Invalid or expired OAuth state. Please restart the authorization flow.</h1></body></html>",
            status_code=400,
        )

    server_name = pending["server_name"]
    created_at = float(pending.get("created_at", "0"))
    if time.time() - created_at > 600:
        return HTMLResponse(
            content="<html><body><h1>OAuth authorization timed out (10 minutes). Please restart.</h1></body></html>",
            status_code=400,
        )

    token_data: dict[str, str] = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": pending["redirect_uri"],
        "client_id": pending["client_id"],
        "code_verifier": pending["code_verifier"],
    }
    if pending["client_secret"]:
        token_data["client_secret"] = pending["client_secret"]

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(pending["token_endpoint"], data=token_data)

            if resp.status_code != 200:
                logger.error(
                    "MCP OAuth token exchange failed for '%s': %d %s",
                    server_name,
                    resp.status_code,
                    resp.text[:300],
                )
                return HTMLResponse(
                    content=f"<html><body><h1>Token exchange failed (HTTP {resp.status_code}).</h1><p>The authorization server rejected the request.</p></body></html>",
                    status_code=400,
                )

            result = resp.json()
            token = MCPOAuthToken(
                access_token=result["access_token"],
                token_type=result.get("token_type", "Bearer"),
                refresh_token=result.get("refresh_token"),
                expires_at=time.time() + result.get("expires_in", 3600),
                scope=result.get("scope") or pending["scope"],
            )

            oauth_config = MCPOAuthConfig(
                authorization_endpoint="",
                token_endpoint=pending["token_endpoint"],
                client_id=pending["client_id"],
                client_secret=pending["client_secret"] or None,
            )
            store = get_mcp_oauth_token_store()
            await store.save_token_with_config(server_name, token, oauth_config)

            _successful_auth[state] = time.time()

            await _refresh_connection_pool_auth(server_name, token)
            logger.info("MCP OAuth completed for '%s'", server_name)
            return HTMLResponse(
                content="""
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
            )

    except httpx.HTTPError as exc:
        logger.error("MCP OAuth token exchange network error: %s", exc)
        return HTMLResponse(
            content=f"<html><body><h1>Network error during token exchange</h1><p>{exc}</p></body></html>", status_code=500
        )


@router.get("/status/{state}")
async def check_mcp_oauth_state_status(state: str) -> JSONResponse:
    """Check if a specific OAuth state has successfully completed."""
    if state in _successful_auth:
        return success_response(data={"status": "success"})
    if state in _pending_auth:
        return success_response(data={"status": "pending"})
    return success_response(data={"status": "expired_or_invalid"})


@router.get("/status")
async def get_mcp_oauth_status() -> JSONResponse:
    """Return OAuth connection status for all MCP servers."""
    store = get_mcp_oauth_token_store()
    statuses = await store.get_all_statuses()
    return success_response(data=statuses)


@router.delete("/{server_name}")
async def disconnect_mcp_oauth(server_name: str) -> JSONResponse:
    """Disconnect (delete) OAuth tokens for an MCP server."""
    store = get_mcp_oauth_token_store()
    await store.delete_token(server_name)
    logger.info("MCP OAuth disconnected for '%s'", server_name)
    return success_response(data={"server_name": server_name, "connected": False})
