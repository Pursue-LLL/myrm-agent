"""Provider OAuth authorization flows for model providers.

Enables users with paid subscriptions (Claude Pro/Max, ChatGPT Plus/Pro,
GitHub Copilot) to authenticate via OAuth instead of API keys.

OAuth tokens are stored as provider-scoped credentials in oauthCredentials,
injected by model_resolver at LLM call time.

[INPUT]
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)

[OUTPUT]
Provider OAuth APIs under /integrations/provider-oauth
  - /anthropic/start  POST  → initiate Anthropic PKCE flow
  - /anthropic/callback GET  → handle Anthropic PKCE callback
  - /openai/start     POST  → initiate OpenAI device-code flow
  - /openai/poll      POST  → poll OpenAI device-code completion
  - /copilot/start    POST  → initiate GitHub Copilot device-code flow
  - /copilot/poll     POST  → poll Copilot device-code completion
  - /status/{provider} GET  → query provider OAuth status
  - /disconnect/{provider} DELETE → disconnect provider OAuth

[POS]
Flat-file API module following xai_oauth.py pattern.
All three flows store credentials via oauth_store with issuer prefix "provider_".
"""

from __future__ import annotations

import hashlib
import logging
import secrets
import time
from base64 import urlsafe_b64encode
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infra.limiter import limiter
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.services.agent.session_credential_assembler import XAI_ISSUER
from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    delete_oauth_credential,
    extract_copilot_base_url,
    is_oauth_issuer_connected,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# ──────────────────────────── Issuer Keys ──────────────────────────────

ANTHROPIC_ISSUER = "provider_anthropic"
OPENAI_ISSUER = "provider_openai"
COPILOT_ISSUER = "provider_copilot"

_ALL_PROVIDER_ISSUERS = {
    "anthropic": ANTHROPIC_ISSUER,
    "openai": OPENAI_ISSUER,
    "copilot": COPILOT_ISSUER,
    "xai": XAI_ISSUER,
}

# ──────────────────────── Anthropic Constants ──────────────────────────

_ANTHROPIC_CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
_ANTHROPIC_AUTHORIZE_URL = "https://claude.ai/oauth/authorize"
_ANTHROPIC_TOKEN_URL = "https://platform.claude.com/v1/oauth/token"
_ANTHROPIC_SCOPES = "org:create_api_key user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload"

# ──────────────────────── OpenAI Constants ──────────────────────────────

_OPENAI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
_OPENAI_AUTH_BASE = "https://auth.openai.com"
_OPENAI_DEVICE_USER_CODE_URL = f"{_OPENAI_AUTH_BASE}/api/accounts/deviceauth/usercode"
_OPENAI_DEVICE_TOKEN_URL = f"{_OPENAI_AUTH_BASE}/api/accounts/deviceauth/token"
_OPENAI_TOKEN_URL = f"{_OPENAI_AUTH_BASE}/oauth/token"
_OPENAI_DEVICE_REDIRECT_URI = f"{_OPENAI_AUTH_BASE}/deviceauth/callback"
_OPENAI_DEVICE_VERIFICATION_URI = f"{_OPENAI_AUTH_BASE}/codex/device"
_OPENAI_SCOPE = "openid profile email offline_access"

# ────────────────────── GitHub Copilot Constants ──────────────────────

_COPILOT_CLIENT_ID = "Iv1.b507a08c87ecfe98"
_COPILOT_HEADERS = {
    "User-Agent": "GitHubCopilotChat/0.35.0",
    "Editor-Version": "vscode/1.107.0",
    "Editor-Plugin-Version": "copilot-chat/0.35.0",
    "Copilot-Integration-Id": "vscode-chat",
}
_COPILOT_API_VERSION = "2026-06-01"

# ──────────────────────── Shared State ─────────────────────────────────

_DEVICE_CODE_TIMEOUT_S = 600


class _PendingDeviceCode(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    expires_at: float
    interval: int
    provider: str
    # OpenAI-specific
    device_auth_id: str = ""


class _PendingPKCE(BaseModel):
    code_verifier: str
    state: str
    redirect_uri: str
    expires_at: float


_pending_device_flows: dict[str, _PendingDeviceCode] = {}
_pending_pkce_flows: dict[str, _PendingPKCE] = {}


def _evict_expired() -> None:
    now = time.time()
    for store in (_pending_device_flows, _pending_pkce_flows):
        expired = [k for k, v in store.items() if now > v.expires_at]
        for k in expired:
            del store[k]


# ──────────────────────── PKCE Helpers ────────────────────────────────


def _generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge (S256)."""
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _oauth_success_html(message: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Authorization Successful</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;
min-height:100vh;margin:0;background:#f9fafb;color:#1a1a2e}}
.card{{text-align:center;padding:3rem;background:white;border-radius:16px;
box-shadow:0 4px 24px rgba(0,0,0,.08);max-width:420px}}
h1{{font-size:1.5rem;margin:0 0 1rem}}p{{color:#666;margin:0}}</style></head>
<body><div class="card"><h1>✓ {message}</h1>
<p>You can close this window and return to Myrm.</p></div></body></html>"""


def _oauth_error_html(message: str) -> str:
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>Authorization Failed</title>
<style>body{{font-family:system-ui,sans-serif;display:flex;justify-content:center;align-items:center;
min-height:100vh;margin:0;background:#fef2f2;color:#991b1b}}
.card{{text-align:center;padding:3rem;background:white;border-radius:16px;
box-shadow:0 4px 24px rgba(0,0,0,.08);max-width:420px}}
h1{{font-size:1.5rem;margin:0 0 1rem}}p{{color:#666;margin:0}}</style></head>
<body><div class="card"><h1>✗ Authorization Failed</h1>
<p>{message}</p></div></body></html>"""


# ═══════════════════════════════════════════════════════════════════════
#  Anthropic OAuth (PKCE + Callback)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/anthropic/start")
@limiter.limit("5/minute")
async def start_anthropic_oauth(request: Request) -> JSONResponse:
    """Initiate Anthropic PKCE authorization flow.

    Returns the authorization URL for the frontend to open in a new browser tab.
    """
    _evict_expired()

    verifier, challenge = _generate_pkce()
    state = secrets.token_urlsafe(32)

    base_url = str(request.base_url).rstrip("/")
    redirect_uri = f"{base_url}/api/integrations/provider-oauth/anthropic/callback"

    params = {
        "code": "true",
        "client_id": _ANTHROPIC_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": _ANTHROPIC_SCOPES,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    authorize_url = f"{_ANTHROPIC_AUTHORIZE_URL}?{urlencode(params)}"

    _pending_pkce_flows[state] = _PendingPKCE(
        code_verifier=verifier,
        state=state,
        redirect_uri=redirect_uri,
        expires_at=time.time() + _DEVICE_CODE_TIMEOUT_S,
    )

    return success_response(
        data={
            "authorize_url": authorize_url,
            "state": state,
        }
    )


@router.get("/anthropic/callback")
async def anthropic_oauth_callback(
    code: str = Query(""),
    state: str = Query(""),
    error: str = Query(""),
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    """Handle Anthropic OAuth PKCE callback.

    Exchanges authorization code for tokens and persists the credential.
    """
    if error:
        return HTMLResponse(_oauth_error_html(f"Anthropic returned an error: {error}"), status_code=400)

    if not code or not state:
        return HTMLResponse(_oauth_error_html("Missing authorization code or state."), status_code=400)

    pending = _pending_pkce_flows.pop(state, None)
    if not pending:
        return HTMLResponse(_oauth_error_html("Invalid or expired authorization state."), status_code=400)

    if time.time() > pending.expires_at:
        return HTMLResponse(_oauth_error_html("Authorization session expired."), status_code=400)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                _ANTHROPIC_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": _ANTHROPIC_CLIENT_ID,
                    "code": code,
                    "state": state,
                    "redirect_uri": pending.redirect_uri,
                    "code_verifier": pending.code_verifier,
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            if resp.status_code != 200:
                logger.error("Anthropic token exchange failed: %d %s", resp.status_code, resp.text)
                return HTMLResponse(
                    _oauth_error_html("Failed to exchange authorization code. Please try again."),
                    status_code=400,
                )

            token_data = resp.json()
    except Exception as exc:
        logger.error("Anthropic token exchange error: %s", exc)
        return HTMLResponse(
            _oauth_error_html("Network error during token exchange. Please try again."),
            status_code=502,
        )

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token", "")
    expires_in = int(token_data.get("expires_in", 3600))

    if not access_token:
        return HTMLResponse(_oauth_error_html("No access token in response."), status_code=400)

    await upsert_oauth_credential(
        db,
        ANTHROPIC_ISSUER,
        {
            "token": access_token,
            "refresh_token": refresh_token,
            "token_url": _ANTHROPIC_TOKEN_URL,
            "client_id": _ANTHROPIC_CLIENT_ID,
            "user_id": "",
            "scope": _ANTHROPIC_SCOPES,
            "expires_at": time.time() + expires_in,
            "provider_id": "anthropic",
        },
    )

    logger.info("Anthropic OAuth PKCE flow completed successfully")
    return HTMLResponse(_oauth_success_html("Anthropic Connected"))


# ═══════════════════════════════════════════════════════════════════════
#  OpenAI OAuth (Device Code)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/openai/start")
@limiter.limit("5/minute")
async def start_openai_oauth(request: Request) -> JSONResponse:
    """Initiate OpenAI device-code authorization flow."""
    _evict_expired()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _OPENAI_DEVICE_USER_CODE_URL,
                json={"client_id": _OPENAI_CLIENT_ID},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("OpenAI device-code request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to initiate OpenAI authorization") from exc

    data = resp.json()
    device_auth_id = str(data.get("device_auth_id", ""))
    user_code = str(data.get("user_code", ""))
    interval = data.get("interval")
    if isinstance(interval, str):
        interval = int(interval.strip())
    interval = int(interval or 5)

    if not device_auth_id or not user_code:
        raise HTTPException(status_code=502, detail="Invalid OpenAI device-code response")

    pending = _PendingDeviceCode(
        device_code=device_auth_id,
        user_code=user_code,
        verification_uri=_OPENAI_DEVICE_VERIFICATION_URI,
        expires_at=time.time() + _DEVICE_CODE_TIMEOUT_S,
        interval=interval,
        provider="openai",
        device_auth_id=device_auth_id,
    )
    _pending_device_flows[user_code] = pending

    return success_response(
        data={
            "user_code": user_code,
            "verification_uri": _OPENAI_DEVICE_VERIFICATION_URI,
            "expires_in": _DEVICE_CODE_TIMEOUT_S,
            "interval": interval,
        }
    )


@router.post("/openai/poll")
@limiter.limit("30/minute")
async def poll_openai_oauth(
    request: Request,
    user_code: str = "",
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Poll for OpenAI device-code authorization completion."""
    pending = _pending_device_flows.get(user_code)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending authorization for this user_code")

    if time.time() > pending.expires_at:
        _pending_device_flows.pop(user_code, None)
        return success_response(data={"status": "expired"})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _OPENAI_DEVICE_TOKEN_URL,
                json={
                    "device_auth_id": pending.device_auth_id,
                    "user_code": user_code,
                },
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.warning("OpenAI device-code poll network error: %s", exc)
        return success_response(data={"status": "pending", "error": "network_error"})

    if resp.status_code == 200:
        data = resp.json()
        auth_code = data.get("authorization_code")
        code_verifier = data.get("code_verifier")

        if not auth_code or not code_verifier:
            return success_response(data={"status": "pending", "error": "incomplete_response"})

        # Exchange authorization code for tokens
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                token_resp = await client.post(
                    _OPENAI_TOKEN_URL,
                    data={
                        "grant_type": "authorization_code",
                        "client_id": _OPENAI_CLIENT_ID,
                        "code": auth_code,
                        "code_verifier": code_verifier,
                        "redirect_uri": _OPENAI_DEVICE_REDIRECT_URI,
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                if token_resp.status_code != 200:
                    logger.error("OpenAI token exchange failed: %d %s", token_resp.status_code, token_resp.text)
                    return success_response(data={"status": "pending", "error": "token_exchange_failed"})

                token_data = token_resp.json()
        except Exception as exc:
            logger.error("OpenAI token exchange error: %s", exc)
            return success_response(data={"status": "pending", "error": "token_exchange_error"})

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 3600))

        if not access_token:
            return success_response(data={"status": "pending", "error": "missing_token"})

        await upsert_oauth_credential(
            db,
            OPENAI_ISSUER,
            {
                "token": access_token,
                "refresh_token": refresh_token,
                "token_url": _OPENAI_TOKEN_URL,
                "client_id": _OPENAI_CLIENT_ID,
                "user_id": "",
                "scope": _OPENAI_SCOPE,
                "expires_at": time.time() + expires_in,
                "provider_id": "openai",
            },
        )

        _pending_device_flows.pop(user_code, None)
        logger.info("OpenAI OAuth device-code flow completed successfully")
        return success_response(data={"status": "success"})

    if resp.status_code in (403, 404):
        return success_response(data={"status": "pending"})

    body = {}
    try:
        body = resp.json()
    except Exception:
        pass

    error_val = body.get("error", "")
    if isinstance(error_val, dict):
        error_code = error_val.get("code", "")
    else:
        error_code = str(error_val)

    if error_code in ("authorization_pending", "deviceauth_authorization_pending"):
        return success_response(data={"status": "pending"})
    if error_code == "slow_down":
        return success_response(data={"status": "pending", "slow_down": True})
    if error_code in ("expired_token", "access_denied"):
        _pending_device_flows.pop(user_code, None)
        return success_response(data={"status": "denied", "error": error_code})

    logger.warning("OpenAI device-code poll unexpected response: %d %s", resp.status_code, body)
    return success_response(data={"status": "pending", "error": error_code or "unknown"})


# ═══════════════════════════════════════════════════════════════════════
#  GitHub Copilot OAuth (Device Code + Token Exchange)
# ═══════════════════════════════════════════════════════════════════════


@router.post("/copilot/start")
@limiter.limit("5/minute")
async def start_copilot_oauth(request: Request) -> JSONResponse:
    """Initiate GitHub Copilot device-code authorization flow."""
    _evict_expired()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://github.com/login/device/code",
                data={
                    "client_id": _COPILOT_CLIENT_ID,
                    "scope": "read:user",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "GitHubCopilotChat/0.35.0",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("GitHub Copilot device-code request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to initiate GitHub Copilot authorization") from exc

    data = resp.json()
    device_code = str(data.get("device_code", ""))
    user_code = str(data.get("user_code", ""))
    verification_uri = str(data.get("verification_uri", "https://github.com/login/device"))
    interval = int(data.get("interval", 5))
    expires_in = int(data.get("expires_in", _DEVICE_CODE_TIMEOUT_S))

    if not device_code or not user_code:
        raise HTTPException(status_code=502, detail="Invalid GitHub device-code response")

    pending = _PendingDeviceCode(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        expires_at=time.time() + expires_in,
        interval=interval,
        provider="copilot",
    )
    _pending_device_flows[f"copilot_{user_code}"] = pending

    return success_response(
        data={
            "user_code": user_code,
            "verification_uri": verification_uri,
            "expires_in": expires_in,
            "interval": interval,
        }
    )


@router.post("/copilot/poll")
@limiter.limit("30/minute")
async def poll_copilot_oauth(
    request: Request,
    user_code: str = "",
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Poll for GitHub Copilot device-code authorization completion.

    After GitHub authorization, exchanges GitHub access token for Copilot token,
    discovers available models, and persists everything.
    """
    key = f"copilot_{user_code}"
    pending = _pending_device_flows.get(key)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending authorization for this user_code")

    if time.time() > pending.expires_at:
        _pending_device_flows.pop(key, None)
        return success_response(data={"status": "expired"})

    # Step 1: Poll GitHub for access token
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": _COPILOT_CLIENT_ID,
                    "device_code": pending.device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "User-Agent": "GitHubCopilotChat/0.35.0",
                },
            )
    except httpx.HTTPError as exc:
        logger.warning("Copilot GitHub token poll network error: %s", exc)
        return success_response(data={"status": "pending", "error": "network_error"})

    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}

    if resp.status_code == 200 and "access_token" in body:
        github_access_token = str(body["access_token"])

        # Step 2: Exchange GitHub token for Copilot token
        try:
            copilot_token, copilot_expires_at, copilot_base_url = await _exchange_copilot_token(github_access_token)
        except Exception as exc:
            logger.error("Copilot token exchange failed: %s", exc)
            _pending_device_flows.pop(key, None)
            return success_response(data={"status": "denied", "error": "copilot_token_exchange_failed"})

        # Step 3: Discover available models
        available_models: list[str] = []
        try:
            available_models = await _fetch_copilot_models(copilot_token, copilot_base_url)
        except Exception as exc:
            logger.warning("Copilot model discovery failed (non-fatal): %s", exc)

        await upsert_oauth_credential(
            db,
            COPILOT_ISSUER,
            {
                "token": copilot_token,
                "refresh_token": github_access_token,
                "user_id": "",
                "scope": "copilot",
                "expires_at": copilot_expires_at,
                "base_url": copilot_base_url,
                "available_models": available_models,
                "provider_id": "copilot",
            },
        )

        _pending_device_flows.pop(key, None)
        logger.info("GitHub Copilot OAuth device-code flow completed successfully")
        return success_response(
            data={
                "status": "success",
                "available_models": available_models,
                "base_url": copilot_base_url,
            }
        )

    error_code = body.get("error", "")
    if error_code == "authorization_pending":
        return success_response(data={"status": "pending"})
    if error_code == "slow_down":
        return success_response(data={"status": "pending", "slow_down": True})
    if error_code in ("expired_token", "access_denied"):
        _pending_device_flows.pop(key, None)
        return success_response(data={"status": "denied", "error": error_code})

    logger.warning("Copilot GitHub token poll unexpected: %d %s", resp.status_code, body)
    return success_response(data={"status": "pending", "error": error_code or "unknown"})


async def _exchange_copilot_token(github_access_token: str) -> tuple[str, float, str]:
    """Exchange GitHub access token for Copilot API token.

    Returns (copilot_token, expires_at_timestamp, base_url).
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            "https://api.github.com/copilot_internal/v2/token",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {github_access_token}",
                **_COPILOT_HEADERS,
            },
        )
        resp.raise_for_status()

    data = resp.json()
    token = str(data["token"])
    expires_at = float(data["expires_at"])
    base_url = extract_copilot_base_url(token)

    return token, expires_at, base_url


async def _fetch_copilot_models(copilot_token: str, base_url: str) -> list[str]:
    """Fetch available model IDs from Copilot API."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        resp = await client.get(
            f"{base_url}/models",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {copilot_token}",
                **_COPILOT_HEADERS,
                "X-GitHub-Api-Version": _COPILOT_API_VERSION,
            },
        )
        resp.raise_for_status()

    data = resp.json()
    items = data.get("data", [])
    models: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        model_id = item.get("id")
        if not isinstance(model_id, str):
            continue
        # Only include picker-enabled models that support tool calls
        if not item.get("model_picker_enabled", False):
            continue
        policy = item.get("policy")
        if isinstance(policy, dict) and policy.get("state") == "disabled":
            continue
        caps = item.get("capabilities")
        if isinstance(caps, dict):
            supports = caps.get("supports")
            if isinstance(supports, dict) and supports.get("tool_calls") is False:
                continue
        models.append(model_id)
    return models


# ──────────────────────── xAI SuperGrok Delegated Routes ────────────────

@router.post("/xai/start")
@limiter.limit("5/minute")
async def start_xai_oauth_provider(request: Request) -> JSONResponse:
    """Initiate xAI SuperGrok device-code authorization flow via provider-oauth."""
    from app.api.integrations.xai_oauth import start_xai_oauth
    return await start_xai_oauth(request)


@router.post("/xai/poll")
@limiter.limit("30/minute")
async def poll_xai_oauth_provider(
    request: Request,
    user_code: str = "",
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Poll for xAI SuperGrok device-code authorization completion via provider-oauth."""
    from app.api.integrations.xai_oauth import poll_xai_oauth
    return await poll_xai_oauth(request, user_code=user_code, db=db)


# ═══════════════════════════════════════════════════════════════════════
#  Shared Endpoints: Status & Disconnect
# ═══════════════════════════════════════════════════════════════════════


@router.get("/status/{provider}")
async def get_provider_oauth_status(
    provider: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return OAuth connection status for a model provider."""
    issuer = _ALL_PROVIDER_ISSUERS.get(provider)
    if not issuer:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    connected = await is_oauth_issuer_connected(db, issuer)
    result: dict[str, object] = {
        "provider": provider,
        "issuer": issuer,
        "connected": connected,
    }

    if connected:
        row = await load_oauth_credentials_row(db)
        if row:
            credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
            cred_val = credentials.get(issuer)
            if isinstance(cred_val, dict):
                result["expires_at"] = cred_val.get("expires_at")
                result["scope"] = cred_val.get("scope")
                if provider == "copilot":
                    result["base_url"] = cred_val.get("base_url")
                    result["available_models"] = cred_val.get("available_models", [])
                elif provider == "xai":
                    result["base_url"] = cred_val.get("base_url", "https://api.x.ai/v1")
                    result["available_models"] = ["grok-2", "grok-2-mini", "grok-beta"]

    return success_response(data=result)


@router.delete("/disconnect/{provider}")
async def disconnect_provider_oauth(
    provider: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Disconnect OAuth credentials for a model provider."""
    issuer = _ALL_PROVIDER_ISSUERS.get(provider)
    if not issuer:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    deleted = await delete_oauth_credential(db, issuer)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"code": 40401, "message": f"Provider '{provider}' is not connected via OAuth"},
        )

    logger.info("Provider OAuth disconnected: %s", provider)
    return success_response(data={"provider": provider, "connected": False})
