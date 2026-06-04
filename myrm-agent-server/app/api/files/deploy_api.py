"""Artifact deployment API.

[INPUT]
- app.database.connection::get_db (POS: Database session)
- app.core.artifacts.listener::ensure_artifact_for_deploy (POS: Deploy artifact resolution)
- app.core.artifacts.listener::resolve_sandbox_file_path (POS: Sandbox path resolution for deploy assets)
- app.core.infra.limiter::limiter (POS: API rate limiting)
- app.services.deploy.deploy_packager::collect_deploy_files (POS: Vault file packaging)
- app.services.deploy.vercel_client::VercelClient (POS: Vercel deploy client)

[OUTPUT]
- router: APIRouter — deploy endpoints, credentials CRUD, WebSocket status stream

[POS]
Provides one-click artifact deployment to Vercel and encrypted credential storage.
"""

import asyncio
import json
import logging
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.api.dependencies import get_workspace_root
from app.config.deploy_mode import is_sandbox
from app.config.settings import settings
from app.core.artifacts.listener import ensure_artifact_for_deploy, resolve_sandbox_file_path
from app.core.infra.limiter import limiter
from app.database.connection import get_db, get_session
from app.database.models.artifact import Artifact
from app.database.models.config import UserConfig
from app.services.config.encryption import get_encryption_service
from app.services.deploy.deploy_packager import collect_deploy_files, validate_deploy_payload
from app.services.deploy.vercel_client import VercelClient

logger = logging.getLogger(__name__)

router = APIRouter()

_VERCEL_CREDENTIALS_KEY = "vercelDeployCredentials"
_PLATFORM_TOKEN_ENV = "VERCEL_PLATFORM_TOKEN"


class DeployRequest(BaseModel):
    token: str = Field(default="", description="Vercel token; falls back to stored credentials")
    platform: str = "vercel"  # Currently only vercel is supported


class VercelCredentialsResponse(BaseModel):
    token: str | None = None
    configured: bool = False
    platform_available: bool = False


class SaveVercelCredentialsRequest(BaseModel):
    token: str = Field(..., min_length=1)


def _get_platform_vercel_token() -> str | None:
    if not is_sandbox():
        return None
    token = os.environ.get(_PLATFORM_TOKEN_ENV, "").strip()
    return token or None


def _vault_object_path(vault: ArtifactVault, vault_uri: str):
    obj_id = vault_uri[len("vault://") :] if vault_uri.startswith("vault://") else vault_uri
    return vault.get_object_path(obj_id)


def _decrypt_vercel_credentials(
    raw_value: object,
    is_encrypted: bool,
) -> dict[str, object]:
    service = get_encryption_service()
    value = raw_value
    if is_encrypted:
        if isinstance(value, str):
            value = service.decrypt(value)
        elif isinstance(value, dict) and "_cipher" in value:
            cipher = value["_cipher"]
            if isinstance(cipher, str):
                value = service.decrypt(cipher)

    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    return value if isinstance(value, dict) else {}


async def _load_vercel_credentials_row(db: AsyncSession) -> UserConfig | None:
    return (
        await db.execute(
            select(UserConfig).where(UserConfig.config_key == _VERCEL_CREDENTIALS_KEY)
        )
    ).scalars().first()


async def _resolve_vercel_token(db: AsyncSession, request_token: str) -> str:
    token = request_token.strip()
    if token:
        return token

    row = await _load_vercel_credentials_row(db)
    if row:
        credentials = _decrypt_vercel_credentials(row.config_value, row.is_encrypted)
        stored_token = credentials.get("token")
        if isinstance(stored_token, str) and stored_token.strip():
            return stored_token.strip()

    platform_token = _get_platform_vercel_token()
    if platform_token:
        return platform_token

    raise HTTPException(
        status_code=400,
        detail="Vercel token is required. Configure it in deploy settings or pass token in request.",
    )


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
    platform_available = _get_platform_vercel_token() is not None
    row = await _load_vercel_credentials_row(db)
    if not row:
        return VercelCredentialsResponse(configured=False, platform_available=platform_available)

    credentials = _decrypt_vercel_credentials(row.config_value, row.is_encrypted)
    token = credentials.get("token")
    if not isinstance(token, str) or not token.strip():
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
    service = get_encryption_service()
    value: dict[str, object] = {"token": payload.token.strip()}
    stored_value, is_encrypted = service.encrypt_if_needed(_VERCEL_CREDENTIALS_KEY, value)
    if is_encrypted and isinstance(stored_value, str):
        stored_value = {"_cipher": stored_value}

    row = await _load_vercel_credentials_row(db)
    if row:
        row.config_value = stored_value
        row.is_encrypted = is_encrypted
        flag_modified(row, "config_value")
    else:
        db.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key=_VERCEL_CREDENTIALS_KEY,
                config_value=stored_value,
                version="1.0.0",
                last_device_id="webui",
                is_encrypted=is_encrypted,
            )
        )

    await db.commit()
    return {"status": "success", "message": "Vercel credentials saved"}


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
    try:
        artifact = await ensure_artifact_for_deploy(db, artifact_id, workspace_root)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    if not artifact.versions:
        raise HTTPException(status_code=400, detail="Artifact has no versions to deploy")

    latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]

    vault = ArtifactVault(workspace_root)
    try:
        obj_path = _vault_object_path(vault, latest_version.vault_uri)
        asset_root: Path | None = None
        if artifact.chat_id and artifact.name:
            resolved = resolve_sandbox_file_path(
                artifact.name, workspace_root, artifact.chat_id
            )
            if resolved:
                asset_root = Path(resolved).parent
        files_to_deploy = collect_deploy_files(
            obj_path,
            asset_root=asset_root,
            entry_name_hint=artifact.name,
        )
        validate_deploy_payload(files_to_deploy)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error("Failed to read artifact files: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to read artifact files: {str(e)}") from e

    vercel_token = await _resolve_vercel_token(db, deploy_body.token)
    client = VercelClient(token=vercel_token)
    try:
        project_name = "".join(c if c.isalnum() or c == "-" else "-" for c in artifact.name.lower())
        if not project_name:
            project_name = f"myrm-artifact-{artifact_id[:8]}"

        deploy_result = await client.deploy(
            project_name=project_name,
            files=files_to_deploy,
            project_id=artifact.deployment_project_id,
        )

        artifact.deployment_url = deploy_result["url"]
        artifact.deployment_project_id = deploy_result["project_id"]
        artifact.deployment_status = deploy_result["status"]
        artifact.deployment_version_id = latest_version.id
        await db.commit()

        return {
            **deploy_result,
            "deployment_url": deploy_result["url"],
            "deployment_status": deploy_result["status"],
            "deployment_project_id": deploy_result.get("project_id"),
            "deployment_version_id": latest_version.id,
            "latest_version_id": latest_version.id,
        }

    except Exception as e:
        logger.error("Deployment failed: %s", e)
        artifact.deployment_status = "ERROR"
        await db.commit()
        raise HTTPException(status_code=500, detail=str(e)) from e


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
            vercel_token = await _resolve_vercel_token(db, "")
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
