"""Shared Vercel artifact deployment executor for REST and Agent paths.

[INPUT]
- app.services.deploy.artifact_files::resolve_artifact_deploy_files (POS: deploy/share 共用文件收集)
- app.services.deploy.preflight::evaluate_deploy_preflight (POS: 文件级部署门禁)
- app.services.deploy.vercel_client::VercelClient (POS: Vercel API v13 客户端)
- app.services.deploy.types::DeployResult (POS: 部署结果数据类)

[OUTPUT]
- sanitize_vercel_project_name: Vercel 项目名规范化
- execute_vercel_artifact_deploy: 统一部署执行（写 artifact 部署字段）

[POS]
REST deploy_api 与 Agent deploy_artifact 的唯一 Vercel 部署执行入口。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.services.deploy.types import DeployResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def sanitize_vercel_project_name(artifact_name: str, artifact_id: str) -> str:
    """Build a Vercel-safe project name from artifact metadata."""
    project_name = "".join(c if c.isalnum() or c == "-" else "-" for c in artifact_name.lower())
    if not project_name:
        project_name = f"myrm-artifact-{artifact_id[:8]}"
    return project_name


async def execute_vercel_artifact_deploy(
    db: AsyncSession,
    artifact_id: str,
    workspace_root: str,
    *,
    vercel_token: str,
) -> DeployResult:
    """Deploy an artifact to Vercel and persist deployment fields on the artifact row."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database.models.artifact import Artifact
    from app.services.deploy.artifact_files import resolve_artifact_deploy_files
    from app.services.deploy.preflight import evaluate_deploy_preflight
    from app.services.deploy.vercel_client import VercelClient

    existing = (
        await db.execute(
            select(Artifact)
            .options(selectinload(Artifact.versions))
            .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
        )
    ).scalars().first()
    if existing is not None and not existing.versions:
        return DeployResult(
            success=False,
            url="",
            deployment_id="",
            project_id="",
            status="PREFLIGHT_FAILED",
            error="Artifact has no versions to deploy.",
        )

    artifact, files = await resolve_artifact_deploy_files(db, artifact_id, workspace_root)

    check = evaluate_deploy_preflight(files)
    if not check.deployable:
        return DeployResult(
            success=False,
            url="",
            deployment_id="",
            project_id="",
            status="PREFLIGHT_FAILED",
            error=check.message,
        )

    latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
    project_name = sanitize_vercel_project_name(artifact.name, artifact_id)
    client = VercelClient(token=vercel_token)

    try:
        deploy_result = await client.deploy(
            project_name=project_name,
            files=files,
            project_id=artifact.deployment_project_id,
        )
    except Exception as exc:
        logger.error("Deployment failed for artifact %s: %s", artifact_id, exc)
        artifact.deployment_status = "ERROR"
        await db.commit()
        return DeployResult(
            success=False,
            url="",
            deployment_id="",
            project_id=artifact.deployment_project_id or "",
            status="ERROR",
            error=str(exc),
        )

    artifact.deployment_url = deploy_result["url"]
    artifact.deployment_project_id = deploy_result["project_id"]
    artifact.deployment_status = deploy_result["status"]
    artifact.deployment_version_id = latest_version.id
    await db.commit()

    return DeployResult(
        success=True,
        url=deploy_result["url"],
        deployment_id=deploy_result.get("deployment_id", ""),
        project_id=deploy_result.get("project_id", ""),
        status=deploy_result.get("status", "READY"),
        latest_version_id=latest_version.id,
    )
