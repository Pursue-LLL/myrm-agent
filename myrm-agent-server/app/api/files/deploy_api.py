"""Artifact deployment API.

[INPUT]
- app.database.connection::get_db (POS: Database session)
- app.database.models.artifact::Artifact (POS: Artifact ORM model)
- app.database.models.config::UserConfig (POS: User config with encryption)
- app.services.config.encryption::get_encryption_service (POS: Config encryption service)
- app.services.deploy.vercel_client::VercelClient (POS: Vercel deploy client)

[OUTPUT]
- router: APIRouter — deploy endpoints, credentials CRUD, WebSocket status stream

[POS]
Provides one-click artifact deployment to Vercel and encrypted credential storage.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from app.api.dependencies import get_workspace_root
from app.database.connection import get_db, get_session
from app.database.models.artifact import Artifact
from app.database.models.config import UserConfig
from app.services.config.encryption import get_encryption_service
from app.services.deploy.vercel_client import VercelClient

logger = logging.getLogger(__name__)

router = APIRouter()

_VERCEL_CREDENTIALS_KEY = "vercelDeployCredentials"


class DeployRequest(BaseModel):
    token: str = Field(default="", description="Vercel token; falls back to stored credentials")
    platform: str = "vercel"  # Currently only vercel is supported


class VercelCredentialsResponse(BaseModel):
    token: str | None = None
    configured: bool = False


class SaveVercelCredentialsRequest(BaseModel):
    token: str = Field(..., min_length=1)


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
    if not row:
        raise HTTPException(
            status_code=400,
            detail="Vercel token is required. Configure it in deploy settings or pass token in request.",
        )

    credentials = _decrypt_vercel_credentials(row.config_value, row.is_encrypted)
    stored_token = credentials.get("token")
    if not isinstance(stored_token, str) or not stored_token.strip():
        raise HTTPException(
            status_code=400,
            detail="Vercel token is required. Configure it in deploy settings or pass token in request.",
        )
    return stored_token.strip()


@router.get("/deploy/credentials/vercel", response_model=VercelCredentialsResponse)
async def get_vercel_credentials(
    db: AsyncSession = Depends(get_db),
) -> VercelCredentialsResponse:
    """Return stored Vercel deploy token (encrypted at rest in UserConfig)."""
    row = await _load_vercel_credentials_row(db)
    if not row:
        return VercelCredentialsResponse(configured=False)

    credentials = _decrypt_vercel_credentials(row.config_value, row.is_encrypted)
    token = credentials.get("token")
    if not isinstance(token, str) or not token.strip():
        return VercelCredentialsResponse(configured=False)

    return VercelCredentialsResponse(token=token, configured=True)


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
async def deploy_artifact(
    artifact_id: str,
    request: DeployRequest,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """Deploy an artifact to a third-party platform (e.g., Vercel)."""
    if request.platform != "vercel":
        raise HTTPException(status_code=400, detail="Only Vercel is supported currently")

    # 1. Fetch Artifact and its latest version
    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    artifact = result.scalars().first()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")
    
    if not artifact.versions:
        raise HTTPException(status_code=400, detail="Artifact has no versions to deploy")

    latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]

    # 2. Read files from Vault
    vault = ArtifactVault(str(get_workspace_root()))
    try:
        obj_path = vault.get_object_path(latest_version.vault_uri)
        if not obj_path.exists():
            raise FileNotFoundError(f"Missing in vault: {obj_path}")
            
        # Assuming the vault object for a web artifact is a directory or a single HTML file.
        # If it's a single file, we wrap it in a dict. If it's a directory, we read all files.
        files_to_deploy = {}
        if obj_path.is_file():
            with open(obj_path, "r", encoding="utf-8") as f:
                content = f.read()
            # If it's a single file, we assume it's index.html for deployment purposes
            file_name = "index.html" if obj_path.suffix in [".html", ".htm"] else obj_path.name
            files_to_deploy[file_name] = content
        elif obj_path.is_dir():
            for file_path in obj_path.rglob("*"):
                if file_path.is_file():
                    rel_path = file_path.relative_to(obj_path).as_posix()
                    with open(file_path, "r", encoding="utf-8") as f:
                        files_to_deploy[rel_path] = f.read()
        else:
            raise HTTPException(status_code=400, detail="Invalid artifact physical format")
            
    except Exception as e:
        logger.error(f"Failed to read artifact files: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to read artifact files: {str(e)}") from e

    # 3. Deploy using VercelClient
    vercel_token = await _resolve_vercel_token(db, request.token)
    client = VercelClient(token=vercel_token)
    try:
        # Use artifact name as project name, sanitize it
        project_name = "".join(c if c.isalnum() or c == "-" else "-" for c in artifact.name.lower())
        if not project_name:
            project_name = f"myrm-artifact-{artifact_id[:8]}"
            
        deploy_result = await client.deploy(project_name=project_name, files=files_to_deploy)
        
        # 4. Update Database
        artifact.deployment_url = deploy_result["url"]
        artifact.deployment_project_id = deploy_result["project_id"]
        artifact.deployment_status = deploy_result["status"]
        await db.commit()
        
        return deploy_result
        
    except Exception as e:
        logger.error(f"Deployment failed: {e}")
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
        logger.warning(f"WebSocket auth timeout for deployment {deployment_id}")
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except json.JSONDecodeError as e:
        logger.warning(f"WebSocket auth JSON decode error: {e}")
        await websocket.close(code=1003, reason="Unsupported Data: Invalid JSON")
        return
    except Exception as e:
        logger.warning(f"WebSocket auth error: {e}")
        await websocket.close(code=1008, reason="Auth failed")
        return

    try:
        async with get_session() as db:
            vercel_token = await _resolve_vercel_token(db, "")
    except HTTPException:
        await websocket.close(code=1008, reason="Missing Vercel credentials")
        return

    client = VercelClient(token=vercel_token)
    
    try:
        while True:
            try:
                status_data = await client.get_deployment_status(deployment_id)
                await websocket.send_json(status_data)
                
                status = status_data.get("status")
                if status in ["READY", "ERROR", "CANCELED"]:
                    break
                    
                await asyncio.sleep(2.0) # Poll every 2 seconds
            except Exception as e:
                logger.error(f"Error polling deployment status: {e}")
                await websocket.send_json({"status": "ERROR", "error": str(e)})
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for deployment {deployment_id}")
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
