"""Artifact hosting and publication API.

[POS] REST endpoints for multi-target artifact publish, preflight, and credentials.

[INPUT]
- app.services.hosting.orchestrator (POS: publication workflow)

[OUTPUT]
- FastAPI routes under /api/v1/files/hosting/*
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_workspace_root
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.database.connection import get_db, get_session
from app.services.hosting.credentials import (
    get_target_credential_status,
    migrate_legacy_vercel_credentials,
    resolve_target_credentials,
    save_target_credentials,
)
from app.services.hosting.orchestrator import publish_artifact_to_target
from app.services.hosting.preflight import run_deploy_preflight
from app.services.hosting.publication_store import list_publications, publication_to_dict
from app.services.hosting.registry import get_hosting_provider
from app.services.hosting.targets import (
    delete_hosting_target,
    get_hosting_target,
    list_hosting_targets,
    upsert_hosting_target,
)
from app.services.hosting.types import HostingTarget, ProviderType

logger = logging.getLogger(__name__)

router = APIRouter()


class HostingTargetPayload(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1, max_length=120)
    provider_type: ProviderType
    config: dict[str, str] = Field(default_factory=dict)
    is_default: bool = False


class SaveTargetCredentialsRequest(BaseModel):
    credentials: dict[str, str] = Field(default_factory=dict)


class PublishRequest(BaseModel):
    target_id: str = Field(..., min_length=1)
    token: str = Field(default="", description="Optional override token for this publish")


class PublishPreflightResponse(BaseModel):
    deployable: bool
    reason: str
    message: str
    hint: str | None = None


class TargetCredentialsResponse(BaseModel):
    configured: bool
    platform_available: bool = False
    credentials: dict[str, str] = Field(default_factory=dict)


def _target_dict(target: HostingTarget) -> dict[str, object]:
    return {
        "id": target.id,
        "name": target.name,
        "provider_type": target.provider_type,
        "config": target.config,
        "is_default": target.is_default,
    }


@router.get("/hosting/targets")
async def get_hosting_targets(db: AsyncSession = Depends(get_db)) -> dict[str, list[dict[str, object]]]:
    await migrate_legacy_vercel_credentials(db)
    targets = await list_hosting_targets(db)
    return {"targets": [_target_dict(t) for t in targets]}


@router.post("/hosting/targets")
async def create_hosting_target(
    payload: HostingTargetPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    target = HostingTarget(
        id=payload.id or str(uuid.uuid4()),
        name=payload.name,
        provider_type=payload.provider_type,
        config=payload.config,
        is_default=payload.is_default,
    )
    saved = await upsert_hosting_target(db, target)
    return _target_dict(saved)


@router.put("/hosting/targets/{target_id}")
async def update_hosting_target(
    target_id: str,
    payload: HostingTargetPayload,
    db: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    existing = await get_hosting_target(db, target_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Hosting target not found.")
    target = HostingTarget(
        id=target_id,
        name=payload.name,
        provider_type=payload.provider_type,
        config=payload.config,
        is_default=payload.is_default,
    )
    saved = await upsert_hosting_target(db, target)
    return _target_dict(saved)


@router.delete("/hosting/targets/{target_id}")
async def remove_hosting_target(target_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    deleted = await delete_hosting_target(db, target_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Hosting target not found.")
    return {"status": "success"}


@router.post("/hosting/targets/{target_id}/test")
async def test_hosting_target(target_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, object]:
    target = await get_hosting_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Hosting target not found.")
    try:
        credentials = await resolve_target_credentials(db, target_id)
    except RuntimeError as exc:
        return {"ok": False, "message": str(exc)}
    provider = get_hosting_provider(target.provider_type)
    ok, message = await provider.test_connection(target, credentials)
    return {"ok": ok, "message": message}


@router.get("/hosting/targets/{target_id}/credentials", response_model=TargetCredentialsResponse)
async def get_target_credentials(target_id: str, db: AsyncSession = Depends(get_db)) -> TargetCredentialsResponse:
    status = await get_target_credential_status(db, target_id)
    safe_creds: dict[str, str] = {}
    if status.configured:
        try:
            creds_raw = await resolve_target_credentials(db, target_id)
            for key, value in creds_raw.items():
                if isinstance(value, str):
                    safe_creds[key] = value
        except RuntimeError:
            pass
    return TargetCredentialsResponse(
        configured=status.configured,
        platform_available=status.platform_available,
        credentials=safe_creds,
    )


@router.put("/hosting/targets/{target_id}/credentials")
async def put_target_credentials(
    target_id: str,
    payload: SaveTargetCredentialsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    target = await get_hosting_target(db, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Hosting target not found.")
    return await save_target_credentials(db, target_id, dict(payload.credentials))


@router.get("/{artifact_id}/publications")
async def get_artifact_publications(artifact_id: str, db: AsyncSession = Depends(get_db)) -> dict[str, list[dict[str, str | None]]]:
    rows = await list_publications(db, artifact_id)
    return {"publications": [publication_to_dict(row) for row in rows]}


@router.get("/{artifact_id}/publish/preflight", response_model=PublishPreflightResponse)
async def publish_preflight(
    artifact_id: str,
    target_id: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> PublishPreflightResponse:
    workspace_root = str(get_workspace_root())
    result = await run_deploy_preflight(db, artifact_id, workspace_root)
    if target_id:
        target = await get_hosting_target(db, target_id)
        if target is None:
            raise HTTPException(status_code=404, detail="Hosting target not found.")
    return PublishPreflightResponse(
        deployable=result.deployable,
        reason=result.reason,
        message=result.message,
        hint=result.hint,
    )


@router.post("/{artifact_id}/publish")
@limiter.limit(settings.rate_limit.artifact_deploy)
async def publish_artifact(
    request: Request,
    artifact_id: str,
    body: PublishRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    workspace_root = str(get_workspace_root())
    await migrate_legacy_vercel_credentials(db)
    result = await publish_artifact_to_target(
        db,
        artifact_id,
        workspace_root,
        hosting_target_id=body.target_id,
        request_token=body.token,
    )
    if not result.success:
        if result.status == "PREFLIGHT_FAILED":
            raise HTTPException(status_code=400, detail=result.error or result.status)
        if result.error == "Artifact not found.":
            raise HTTPException(status_code=400, detail="Artifact not found.")
        raise HTTPException(status_code=500, detail=result.error or "Publication failed")
    return {
        "publication_id": result.publication_id,
        "deployment_id": result.publication_id,
        "url": result.url,
        "project_ref": result.project_ref,
        "status": result.status,
        "publication_url": result.url,
        "publication_status": result.status,
        "publication_project_ref": result.project_ref,
        "publication_version_id": result.latest_version_id,
        "latest_version_id": result.latest_version_id,
        "hosting_target_id": body.target_id,
        "deployment_url": result.url,
        "deployment_status": result.status,
        "deployment_project_id": result.project_ref,
        "deployment_version_id": result.latest_version_id,
    }


@router.websocket("/{artifact_id}/publish/status/{publication_id}")
async def publication_status_ws(
    websocket: WebSocket,
    artifact_id: str,
    publication_id: str,
    target_id: str = Query(...),
) -> None:
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
            target = await get_hosting_target(db, target_id)
            if target is None:
                await websocket.close(code=1008, reason="Target not found")
                return
            credentials = await resolve_target_credentials(db, target_id)
            provider = get_hosting_provider(target.provider_type)
    except HTTPException:
        await websocket.close(code=1008, reason="Missing credentials")
        return

    try:
        while True:
            status_data = await provider.poll_status(
                target=target,
                credentials=credentials,
                publication_id=publication_id,
            )
            await websocket.send_json(status_data)
            status = status_data.get("status")
            if status in ["READY", "ERROR", "CANCELED", "ready"]:
                break
            await asyncio.sleep(2.0)
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for publication %s", publication_id)
    except Exception as exc:
        logger.error("Publication status poll error: %s", exc)
        await websocket.send_json({"status": "ERROR", "error": str(exc)})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
