"""Provider OAuth endpoints for model providers (xAI SuperGrok).

Lets a SuperGrok subscription authenticate through OAuth instead of an API key.
The token is stored as a provider-scoped credential in oauthCredentials and
injected by config_loader at LLM call time.

[INPUT]
- app.api.integrations.xai_oauth (POS: xAI device-code flow that /xai/* delegates to)
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)

[OUTPUT]
Provider OAuth APIs under /integrations/provider-oauth
  - /xai/start             POST   → initiate xAI SuperGrok device-code flow
  - /xai/poll              POST   → poll xAI device-code completion
  - /status/{provider}     GET    → query provider OAuth status
  - /disconnect/{provider} DELETE → disconnect provider OAuth

[POS]
Provider-facing facade over the xAI OAuth flow plus the shared status / disconnect
endpoints used by the Models page.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
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

_ALL_PROVIDER_ISSUERS = {"xai": XAI_ISSUER}


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
                if provider == "xai":
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


# ═══════════════════════════════════════════════════════════════════════
#  Test-Only Fixture Endpoints for Chrome E2E
# ═══════════════════════════════════════════════════════════════════════


@router.post("/test/seed-oauth", include_in_schema=False)
async def seed_test_provider_oauth(
    provider: str = "xai",
    token: str = "e2e-test-oauth-token",
    base_url: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Local dev/test only: seed an OAuth credential into oauthStore for E2E verification."""
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    issuer = _ALL_PROVIDER_ISSUERS.get(provider)
    if not issuer:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    cred_data: dict[str, object] = {
        "token": token,
        "connected_at": int(time.time()),
        "expires_at": int(time.time()) + 86400,
    }
    if base_url:
        cred_data["base_url"] = base_url
    elif provider == "xai":
        cred_data["base_url"] = "https://api.x.ai/v1"
        cred_data["available_models"] = ["grok-2", "grok-2-mini"]

    await upsert_oauth_credential(db, issuer, cred_data)
    return success_response(data={"provider": provider, "issuer": issuer, "seeded": True})


@router.post("/test/cleanup-oauth", include_in_schema=False)
async def cleanup_test_provider_oauth(
    provider: str = "xai",
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Local dev/test only: cleanup seeded OAuth credential from oauthStore."""
    from app.config.deploy_mode import is_local_mode

    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    issuer = _ALL_PROVIDER_ISSUERS.get(provider)
    if not issuer:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    await delete_oauth_credential(db, issuer)
    return success_response(data={"provider": provider, "issuer": issuer, "cleaned": True})
