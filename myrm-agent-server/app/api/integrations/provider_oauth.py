"""Provider OAuth endpoints for model providers (xAI SuperGrok).

Lets a SuperGrok subscription authenticate through OAuth instead of an API key.
The token is stored as a provider-scoped credential in oauthCredentials and
injected by config_loader at LLM call time. The device-code login itself lives
in ``xai_oauth`` (/integrations/xai/oauth).

[INPUT]
- app.services.agent.provider_oauth_tokens::PROVIDER_OAUTH_ISSUERS (POS: provider id → issuer registry)
- app.services.integrations.oauth_store (POS: encrypted oauthCredentials persistence)

[OUTPUT]
Provider OAuth APIs under /integrations/provider-oauth
  - /status/{provider}     GET    → query provider OAuth status
  - /disconnect/{provider} DELETE → disconnect provider OAuth

[POS]
Shared status / disconnect endpoints used by the Models page, the Credentials page and the startup
reconciliation of the stored login flags, plus local-only E2E seeding.
"""

from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.services.agent.provider_oauth_tokens import PROVIDER_OAUTH_ISSUERS
from app.services.integrations.oauth_store import (
    decrypt_oauth_credentials,
    delete_oauth_credential,
    is_oauth_issuer_connected,
    load_oauth_credentials_row,
    upsert_oauth_credential,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ═══════════════════════════════════════════════════════════════════════
#  Shared Endpoints: Status & Disconnect
# ═══════════════════════════════════════════════════════════════════════


@router.get("/status/{provider}")
async def get_provider_oauth_status(
    provider: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return OAuth connection status for a model provider."""
    issuer = PROVIDER_OAUTH_ISSUERS.get(provider)
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

    return success_response(data=result)


@router.delete("/disconnect/{provider}")
async def disconnect_provider_oauth(
    provider: str,
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Disconnect OAuth credentials for a model provider."""
    issuer = PROVIDER_OAUTH_ISSUERS.get(provider)
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

    issuer = PROVIDER_OAUTH_ISSUERS.get(provider)
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

    issuer = PROVIDER_OAUTH_ISSUERS.get(provider)
    if not issuer:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    await delete_oauth_credential(db, issuer)
    return success_response(data={"provider": provider, "issuer": issuer, "cleaned": True})
