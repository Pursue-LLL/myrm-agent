"""Artifact deployment API.

[INPUT]
- app.database.connection::get_db (POS: Database session)
- app.core.artifacts.listener::ensure_artifact_for_deploy (POS: Deploy artifact resolution)
- app.core.artifacts.listener::resolve_sandbox_file_path (POS: Sandbox path resolution for deploy assets)
- app.core.infra.limiter::limiter (POS: API rate limiting)
- app.services.deploy.deploy_packager::collect_deploy_files (POS: Vault file packaging)
- app.services.deploy.vercel_client::VercelClient (POS: Vercel deploy client)
- app.services.deploy.credentials (POS: Vercel token SSOT)
- app.services.deploy.vercel_artifact_deploy::execute_vercel_artifact_deploy (POS: Shared deploy executor)

[OUTPUT]
- router: APIRouter — deploy endpoints, credentials CRUD, WebSocket status stream

[POS]
Provides one-click artifact deployment to Vercel and encrypted credential storage.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_workspace_root
from app.config.settings import settings
from app.core.infra.limiter import limiter
from app.database.connection import get_db, get_session
from app.database.models.artifact import Artifact
from app.services.deploy.credentials import (
    decrypt_vercel_credentials,
    get_platform_vercel_token,
    load_vercel_credentials_row,
    resolve_vercel_token,
    save_vercel_credentials as persist_vercel_credentials,
    token_from_credentials_dict,
)
from app.services.deploy.preflight import run_deploy_preflight
from app.services.deploy.vercel_artifact_deploy import execute_vercel_artifact_deploy
from app.services.deploy.vercel_client import VercelClient

logger = logging.getLogger(__name__)

router = APIRouter()


class DeployRequest(BaseModel):
    token: str = Field(default="", description="Vercel token; falls back to stored credentials")
    platform: str = "vercel"  # Currently only vercel is supported


class VercelCredentialsResponse(BaseModel):
    token: str | None = None
    configured: bool = False
    platform_available: bool = False


class SaveVercelCredentialsRequest(BaseModel):
    token: str = Field(..., min_length=1)


class DeployPreflightResponse(BaseModel):
    deployable: bool
    reason: str
    message: str
    hint: str | None = None


async def _resolve_vercel_token_for_api(db: AsyncSession, request_token: str) -> str:
    """Resolve Vercel token and map missing-token errors to HTTP 400."""
    try:
        return await resolve_vercel_token(db, request_token)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=400,
            detail="Vercel token is required. Configure it in deploy settings or pass token in request.",
        ) from exc


async def _apply_deployment_state(
    db: AsyncSession,
    artifact_id: str,
    *,
    deployment_url: str | None,
    deployment_status: str,
    deployment_project_id: str | None = None,
    deployment_version_id: str | None = None,
) -> None:
    stmt = select(Artifact).where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    result = await db.execute(stmt)
    artifact = result.scalars().first()
    if not artifact:
        return

    artifact.deployment_status = deployment_status
    if deployment_url is not None:
        artifact.deployment_url = deployment_url
    if deployment_project_id is not None:
        artifact.deployment_project_id = deployment_project_id
    if deployment_version_id is not None:
        artifact.deployment_version_id = deployment_version_id
    await db.commit()


@router.get("/deploy/credentials/vercel", response_model=VercelCredentialsResponse)
async def get_vercel_credentials(
    db: AsyncSession = Depends(get_db),
) -> VercelCredentialsResponse:
    """Return stored Vercel deploy token (encrypted at rest in UserConfig)."""
    platform_available = get_platform_vercel_token() is not None
    row = await load_vercel_credentials_row(db)
    if not row:
        return VercelCredentialsResponse(configured=False, platform_available=platform_available)

    credentials = decrypt_vercel_credentials(row.config_value, row.is_encrypted)
    token = token_from_credentials_dict(credentials)
    if token is None:
        return VercelCredentialsResponse(configured=False, platform_available=platform_available)

    return VercelCredentialsResponse(
        token=token,
        configured=True,
        platform_available=platform_available,
    )


@router.put("/deploy/credentials/vercel")
async def save_vercel_credentials(
    payload: SaveVercelCredentialsRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Persist Vercel deploy token in UserConfig with encryption."""
    return await persist_vercel_credentials(db, payload.token)


@router.get("/{artifact_id}/deploy/preflight", response_model=DeployPreflightResponse)
async def deploy_artifact_preflight(
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> DeployPreflightResponse:
    """Check whether an artifact can be deployed before opening the deploy UI."""
    workspace_root = str(get_workspace_root())
    result = await run_deploy_preflight(db, artifact_id, workspace_root)
    return DeployPreflightResponse(
        deployable=result.deployable,
        reason=result.reason,
        message=result.message,
        hint=result.hint,
    )


@router.post("/{artifact_id}/deploy")
@limiter.limit(settings.rate_limit.artifact_deploy)
async def deploy_artifact(
    request: Request,
    artifact_id: str,
    deploy_body: DeployRequest,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Deploy an artifact to a third-party platform (e.g., Vercel)."""
    if deploy_body.platform != "vercel":
        raise HTTPException(status_code=400, detail="Only Vercel is supported currently")

    workspace_root = str(get_workspace_root())
    vercel_token = await _resolve_vercel_token_for_api(db, deploy_body.token)

    try:
        result = await execute_vercel_artifact_deploy(
            db,
            artifact_id,
            workspace_root,
            vercel_token=vercel_token,
        )
    except LookupError as e:
        raise HTTPException(status_code=400, detail="Artifact not found.") from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except ValueError as e:
        if str(e) == "NO_VERSIONS":
            raise HTTPException(
                status_code=400,
                detail="Artifact has no versions to deploy.",
            ) from e
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to read artifact files: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to read artifact files: {str(e)}") from e

    if not result.success:
        if result.status == "PREFLIGHT_FAILED":
            raise HTTPException(status_code=400, detail=result.error or result.status)
        raise HTTPException(status_code=500, detail=result.error or "Deployment failed")

    return {
        "deployment_id": result.deployment_id,
        "url": result.url,
        "project_id": result.project_id,
        "status": result.status,
        "deployment_url": result.url,
        "deployment_status": result.status,
        "deployment_project_id": result.project_id,
        "deployment_version_id": result.latest_version_id,
        "latest_version_id": result.latest_version_id,
    }


@router.websocket("/{artifact_id}/deploy/status/{deployment_id}")
async def deployment_status_ws(
    websocket: WebSocket,
    artifact_id: str,
    deployment_id: str,
):
    """WebSocket endpoint to stream deployment status.

    Client sends first message: {"type": "auth"}.
    Vercel token is resolved server-side from encrypted UserConfig storage.
    """
    await websocket.accept()

    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth":
            await websocket.close(code=1008, reason="Invalid auth payload")
            return
    except asyncio.TimeoutError:
        logger.warning("WebSocket auth timeout for deployment %s", deployment_id)
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except json.JSONDecodeError as e:
        logger.warning("WebSocket auth JSON decode error: %s", e)
        await websocket.close(code=1003, reason="Unsupported Data: Invalid JSON")
        return
    except Exception as e:
        logger.warning("WebSocket auth error: %s", e)
        await websocket.close(code=1008, reason="Auth failed")
        return

    try:
        async with get_session() as db:
            vercel_token = await _resolve_vercel_token_for_api(db, "")
            stmt = select(Artifact.id).where(
                Artifact.id == artifact_id,
                Artifact.is_deleted.is_(False),
            )
            if (await db.execute(stmt)).scalar_one_or_none() is None:
                await websocket.close(code=1008, reason="Artifact not found")
                return
    except HTTPException:
        await websocket.close(code=1008, reason="Missing Vercel credentials")
        return

    client = VercelClient(token=vercel_token)
    terminal_status: str | None = None
    terminal_url: str | None = None

    try:
        while True:
            try:
                status_data = await client.get_deployment_status(deployment_id)
                await websocket.send_json(status_data)

                status = status_data.get("status")
                if status in ["READY", "ERROR", "CANCELED"]:
                    terminal_status = str(status)
                    terminal_url = status_data.get("url")
                    break

                await asyncio.sleep(2.0)
            except Exception as e:
                logger.error("Error polling deployment status: %s", e)
                await websocket.send_json({"status": "ERROR", "error": str(e)})
                terminal_status = "ERROR"
                break

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for deployment %s", deployment_id)
    finally:
        if terminal_status is not None:
            try:
                async with get_session() as db:
                    await _apply_deployment_state(
                        db,
                        artifact_id,
                        deployment_url=terminal_url,
                        deployment_status=terminal_status,
                    )
            except Exception as e:
                logger.error("Failed to persist deployment terminal state: %s", e)
        try:
            await websocket.close()
        except Exception:
            pass
