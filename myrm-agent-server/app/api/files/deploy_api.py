import asyncio
import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import get_workspace_root
from app.database.connection import get_db
from app.database.models.artifact import Artifact
from app.services.deploy.vercel_client import VercelClient

logger = logging.getLogger(__name__)

router = APIRouter()

class DeployRequest(BaseModel):
    token: str
    platform: str = "vercel"  # Currently only vercel is supported

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
        raise HTTPException(status_code=500, detail=f"Failed to read artifact files: {str(e)}")

    # 3. Deploy using VercelClient
    client = VercelClient(token=request.token)
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
        raise HTTPException(status_code=500, detail=str(e))

@router.websocket("/{artifact_id}/deploy/status/{deployment_id}")
async def deployment_status_ws(
    websocket: WebSocket,
    artifact_id: str,
    deployment_id: str,
):
    """WebSocket endpoint to stream deployment status.
    Requires first message to be JSON payload: {"type": "auth", "token": "..."}
    """
    await websocket.accept()
    
    # 1. Wait for auth payload
    try:
        auth_msg = await asyncio.wait_for(websocket.receive_json(), timeout=5.0)
        if not isinstance(auth_msg, dict) or auth_msg.get("type") != "auth" or not auth_msg.get("token"):
            await websocket.close(code=1008, reason="Invalid auth payload")
            return
        token = auth_msg["token"]
    except asyncio.TimeoutError:
        logger.warning(f"WebSocket auth timeout for deployment {deployment_id}")
        await websocket.close(code=1008, reason="Auth timeout")
        return
    except Exception as e:
        logger.warning(f"WebSocket auth error: {e}")
        await websocket.close(code=1008, reason="Auth failed")
        return

    client = VercelClient(token=token)
    
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
        except:
            pass
