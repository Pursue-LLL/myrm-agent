"""Legacy Vercel deploy API routes (backward-compatible with DeployModal).

[POS] Shim legacy /deploy/* paths onto multi-target hosting services.

[INPUT]
- app.api.files.hosting_api (POS: shared publish/preflight handlers)

[OUTPUT]
- FastAPI routes mirroring pre-hosting deploy endpoints
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.files.hosting_api import PublishPreflightResponse, PublishRequest
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.database.connection import get_db, get_session
from app.services.hosting.credentials import (
    get_target_credential_status,
    migrate_legacy_vercel_credentials,
    resolve_target_credentials,
    save_target_credentials,
    token_from_credentials,
)
from app.services.hosting.targets import get_default_hosting_target, upsert_hosting_target
from app.services.hosting.types import HostingTarget

logger = logging.getLogger(__name__)

router = APIRouter()


class LegacyDeployRequest(BaseModel):
    token: str = ""
    platform: str = "vercel"
    target_id: str | None = None


@router.get("/deploy/credentials/vercel")
async def legacy_get_vercel_credentials(db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    await migrate_legacy_vercel_credentials(db)
    default = await get_default_hosting_target(db)
    if default is None:
        return {"configured": False, "platform_available": False, "token": None}
    status = await get_target_credential_status(db, default.id)
    token: str | None = None
    if status.configured:
        creds = await resolve_target_credentials(db, default.id)
        token = token_from_credentials(creds)
    return {
        "token": token,
        "configured": status.configured,
        "platform_available": status.platform_available,
    }


@router.put("/deploy/credentials/vercel")
async def legacy_save_vercel_credentials(
    payload: dict[str, str],
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    token = payload.get("token", "").strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token is required.")
    await migrate_legacy_vercel_credentials(db)
    default = await get_default_hosting_target(db)
    if default is None:
        default = await upsert_hosting_target(
            db,
            HostingTarget(
                id=str(uuid.uuid4()),
                name="Vercel",
                provider_type="vercel",
                config={},
                is_default=True,
            ),
        )
    return await save_target_credentials(db, default.id, {"token": token})


@router.get("/{artifact_id}/deploy/preflight", response_model=PublishPreflightResponse)
async def legacy_deploy_preflight(artifact_id: str, db: AsyncSession = Depends(get_db)) -> PublishPreflightResponse:
    from app.api.files.hosting_api import publish_preflight

    return await publish_preflight(artifact_id, None, db)


@router.post("/{artifact_id}/deploy")
@limiter.limit(settings.rate_limit.artifact_deploy)
async def legacy_deploy_artifact(
    request: Request,
    artifact_id: str,
    deploy_body: LegacyDeployRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from app.api.files.hosting_api import publish_artifact

    if deploy_body.platform != "vercel":
        raise HTTPException(status_code=400, detail="Only Vercel is supported currently")
    await migrate_legacy_vercel_credentials(db)
    default = await get_default_hosting_target(db)
    if default is None:
        raise HTTPException(status_code=400, detail="Configure a hosting target in Settings first.")
    return await publish_artifact(
        request,
        artifact_id,
        PublishRequest(target_id=deploy_body.target_id or default.id, token=deploy_body.token),
        db,
    )


@router.websocket("/{artifact_id}/deploy/status/{deployment_id}")
async def legacy_deployment_status_ws(
    websocket: WebSocket,
    artifact_id: str,
    deployment_id: str,
) -> None:
    """Legacy Vercel deployment status WebSocket for existing DeployModal clients."""
    from app.services.hosting.vercel_client import VercelClient

    await websocket.accept()
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth":
            await websocket.close(code=1008, reason="Invalid auth payload")
            return
    except asyncio.TimeoutError:
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except json.JSONDecodeError:
        await websocket.close(code=1003, reason="Unsupported Data: Invalid JSON")
        return

    try:
        async with get_session() as db:
            await migrate_legacy_vercel_credentials(db)
            default = await get_default_hosting_target(db)
            if default is None:
                await websocket.close(code=1008, reason="No hosting target")
                return
            credentials = await resolve_target_credentials(db, default.id)
            token = token_from_credentials(credentials)
            if not token:
                await websocket.close(code=1008, reason="Missing credentials")
                return
    except HTTPException:
        await websocket.close(code=1008, reason="Missing credentials")
        return

    client = VercelClient(token=token)
    try:
        while True:
            status_data = await client.get_deployment_status(deployment_id)
            await websocket.send_json(status_data)
            status = status_data.get("status")
            if status in ["READY", "ERROR", "CANCELED"]:
                break
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        logger.info("Legacy WebSocket disconnected for deployment %s", deployment_id)
    except Exception as exc:
        logger.error("Legacy deployment status poll error: %s", exc)
        await websocket.send_json({"status": "ERROR", "error": str(exc)})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
