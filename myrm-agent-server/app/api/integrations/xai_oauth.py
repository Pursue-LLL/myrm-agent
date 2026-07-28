"""xAI OAuth device-code authorization flow for SuperGrok subscribers.

[INPUT]
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)
- app.services.agent.session_credential_assembler::XAI_ISSUER (POS: canonical issuer key)

[OUTPUT]
xAI OAuth API under /integrations/xai/oauth

[POS]
HTTP routes for xAI device-code OAuth. Allows SuperGrok subscribers to authorize
access to xAI services (X Search, Image/Video Gen, TTS, STT) without an API Key.
Tokens are persisted via the shared oauth_store infrastructure with auto-refresh.
"""

from __future__ import annotations

import logging
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infra.limiter import limiter
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.services.agent.session_credential_assembler import XAI_ISSUER
from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    delete_oauth_credential,
    is_oauth_issuer_connected,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter()

XAI_OAUTH_ISSUER_URL = "https://auth.x.ai"
XAI_OAUTH_CLIENT_ID = "b1a00492-073a-47ea-816f-4c329264a828"
XAI_OAUTH_SCOPE = "openid profile email offline_access grok-cli:access api:access"
XAI_OAUTH_DEVICE_CODE_URL = f"{XAI_OAUTH_ISSUER_URL}/oauth2/device/code"
XAI_OAUTH_TOKEN_URL = f"{XAI_OAUTH_ISSUER_URL}/oauth2/token"
XAI_OAUTH_BASE_URL = "https://api.x.ai/v1"

_DEVICE_CODE_TIMEOUT_S = 600


class _DeviceCodePending(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_at: float
    interval: int


_pending_flows: dict[str, _DeviceCodePending] = {}


def _evict_expired_pending() -> None:
    """Remove expired pending flows to prevent memory accumulation."""
    now = time.time()
    expired = [k for k, v in _pending_flows.items() if now > v.expires_at]
    for k in expired:
        del _pending_flows[k]


@router.post("/start")
@limiter.limit("5/minute")
async def start_xai_oauth(request: Request) -> JSONResponse:
    """Initiate xAI device-code authorization flow.

    Returns the user_code and verification URL for the user to complete in their browser.
    """
    _evict_expired_pending()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                XAI_OAUTH_DEVICE_CODE_URL,
                data={
                    "client_id": XAI_OAUTH_CLIENT_ID,
                    "scope": XAI_OAUTH_SCOPE,
                },
                headers={"Accept": "application/json"},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("xAI device-code request failed: %s", exc)
        raise HTTPException(status_code=502, detail="Failed to initiate xAI authorization") from exc

    data = resp.json()
    device_code = str(data["device_code"])
    user_code = str(data["user_code"])
    verification_uri = str(data.get("verification_uri", "https://auth.x.ai/device"))
    verification_uri_complete = str(data.get("verification_uri_complete", verification_uri))
    interval = int(data.get("interval", 5))
    expires_in = int(data.get("expires_in", _DEVICE_CODE_TIMEOUT_S))

    pending = _DeviceCodePending(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        verification_uri_complete=verification_uri_complete,
        expires_at=time.time() + expires_in,
        interval=interval,
    )
    _pending_flows[user_code] = pending

    return success_response(
        data={
            "user_code": user_code,
            "verification_uri": verification_uri,
            "verification_uri_complete": verification_uri_complete,
            "expires_in": expires_in,
            "interval": interval,
        }
    )


@router.post("/poll")
@limiter.limit("30/minute")
async def poll_xai_oauth(
    request: Request,
    user_code: str = "",
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Poll for device-code authorization completion.

    Called by the frontend at the recommended interval until the user completes
    authorization in their browser or the flow expires.
    """
    pending = _pending_flows.get(user_code)
    if not pending:
        raise HTTPException(status_code=404, detail="No pending authorization for this user_code")

    if time.time() > pending.expires_at:
        _pending_flows.pop(user_code, None)
        return success_response(data={"status": "expired"})

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                XAI_OAUTH_TOKEN_URL,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": pending.device_code,
                    "client_id": XAI_OAUTH_CLIENT_ID,
                },
                headers={"Accept": "application/json"},
            )
    except httpx.HTTPError as exc:
        logger.warning("xAI token poll network error: %s", exc)
        return success_response(data={"status": "pending", "error": "network_error"})

    if resp.status_code == 200:
        token_data = resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            return success_response(data={"status": "pending", "error": "missing_token"})

        refresh_token = token_data.get("refresh_token", "")
        expires_in = int(token_data.get("expires_in", 21600))
        scope = str(token_data.get("scope", XAI_OAUTH_SCOPE))

        await upsert_oauth_credential(
            db,
            XAI_ISSUER,
            {
                "token": str(access_token),
                "refresh_token": refresh_token,
                "token_url": XAI_OAUTH_TOKEN_URL,
                "client_id": XAI_OAUTH_CLIENT_ID,
                "user_id": "",
                "scope": scope,
                "expires_at": time.time() + expires_in,
                "base_url": XAI_OAUTH_BASE_URL,
            },
        )

        _pending_flows.pop(user_code, None)
        logger.info("xAI OAuth device-code flow completed successfully")
        return success_response(data={"status": "success"})

    body = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    error_code = body.get("error", "")

    if error_code == "authorization_pending":
        return success_response(data={"status": "pending"})
    if error_code == "slow_down":
        return success_response(data={"status": "pending", "slow_down": True})
    if error_code in ("expired_token", "access_denied"):
        _pending_flows.pop(user_code, None)
        return success_response(data={"status": "denied", "error": error_code})

    logger.warning("xAI token poll unexpected response: %d %s", resp.status_code, body)
    return success_response(data={"status": "pending", "error": error_code or "unknown"})


@router.get("/status")
async def get_xai_oauth_status(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Return xAI OAuth connection status."""
    connected = await is_oauth_issuer_connected(db, XAI_ISSUER)
    if not connected:
        return success_response(
            data={
                "issuer": XAI_ISSUER,
                "connected": False,
                "scope": None,
                "expires_at": None,
            }
        )

    row = await load_oauth_credentials_row(db)
    if row is None:
        return success_response(
            data={"issuer": XAI_ISSUER, "connected": False, "scope": None, "expires_at": None}
        )

    credentials = decrypt_oauth_credentials(row.config_value, row.is_encrypted)
    cred_val = credentials.get(XAI_ISSUER)
    if not isinstance(cred_val, dict):
        return success_response(
            data={"issuer": XAI_ISSUER, "connected": False, "scope": None, "expires_at": None}
        )

    return success_response(
        data={
            "issuer": XAI_ISSUER,
            "connected": True,
            "scope": cred_val.get("scope"),
            "expires_at": cred_val.get("expires_at"),
        }
    )


@router.delete("")
async def disconnect_xai_oauth(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Disconnect xAI OAuth credentials."""
    deleted = await delete_oauth_credential(db, XAI_ISSUER)
    if not deleted:
        raise HTTPException(status_code=404, detail="xAI SuperGrok is not connected")
    logger.info("xAI OAuth disconnected")
    return success_response(data={"issuer": XAI_ISSUER, "connected": False})
