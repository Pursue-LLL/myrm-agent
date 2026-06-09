"""Agent-facing deployment service implementing the harness DeployBackend protocol.

Bridges the harness ``DeployBackend`` Protocol with existing deployment
infrastructure (``VercelClient``, ``preflight``, ``artifact_files``).
All credential resolution, file collection, and Vercel API calls are
delegated to the existing production-tested modules — zero duplication.

[INPUT]
- myrm_agent_harness.toolkits.deploy::DeployBackend (POS: harness Protocol contract)
- app.services.deploy.preflight::run_deploy_preflight (POS: deploy gate)
- app.services.deploy.artifact_files::resolve_artifact_deploy_files (POS: vault file collection)
- app.services.deploy.vercel_client::VercelClient (POS: Vercel API)
- app.services.deploy.preflight::evaluate_deploy_preflight (POS: file-level check)

[OUTPUT]
- AgentDeployService: concrete DeployBackend for tool_setup.py

[POS]
Server-layer implementation of the harness deploy protocol.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from myrm_agent_harness.toolkits.deploy.deploy_agent_tools import DeployResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class AgentDeployService:
    """Implements ``DeployBackend`` by reusing existing deploy infrastructure.

    Each ``GeneralAgent`` session creates one instance bound to a workspace.
    """

    def __init__(self, workspace_root: str) -> None:
        self._workspace_root = workspace_root

    async def preflight(self, artifact_id: str) -> tuple[bool, str]:
        """Run deploy preflight check for the given artifact."""
        from app.database.connection import get_session
        from app.services.deploy.preflight import run_deploy_preflight

        async with get_session() as db:
            result = await run_deploy_preflight(db, artifact_id, self._workspace_root)
        return result.deployable, result.message

    async def execute_deploy(self, artifact_id: str) -> DeployResult:
        """Execute Vercel deployment, reusing the same flow as deploy_api.py."""
        from app.database.connection import get_session
        from app.services.deploy.artifact_files import resolve_artifact_deploy_files
        from app.services.deploy.preflight import evaluate_deploy_preflight
        from app.services.deploy.vercel_client import VercelClient

        async with get_session() as db:
            artifact, files = await resolve_artifact_deploy_files(db, artifact_id, self._workspace_root)

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

            vercel_token = await self._resolve_token(db)

            client = VercelClient(token=vercel_token)
            project_name = "".join(c if c.isalnum() or c == "-" else "-" for c in artifact.name.lower())
            if not project_name:
                project_name = f"myrm-artifact-{artifact_id[:8]}"

            deploy_result = await client.deploy(
                project_name=project_name,
                files=files,
                project_id=artifact.deployment_project_id,
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
            )

    async def get_artifact_name(self, artifact_id: str) -> str | None:
        """Return the artifact's display name."""
        from sqlalchemy import select

        from app.database.connection import get_session
        from app.database.models.artifact import Artifact

        async with get_session() as db:
            row = await db.execute(
                select(Artifact.name).where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
            )
            return row.scalar_one_or_none()

    async def _resolve_token(self, db: AsyncSession) -> str:
        """Resolve Vercel token from encrypted storage or platform env.

        Reuses the same priority logic as deploy_api.py:
        1. UserConfig encrypted storage (user's BYOK token)
        2. Platform env var (VERCEL_PLATFORM_TOKEN, CP-injected for SaaS)
        """
        import json
        import os

        from sqlalchemy import select

        from app.config.deploy_mode import is_sandbox
        from app.database.models.config import UserConfig
        from app.services.config.encryption import get_encryption_service

        _KEY = "vercelDeployCredentials"
        row = (await db.execute(select(UserConfig).where(UserConfig.config_key == _KEY))).scalars().first()
        if row:
            service = get_encryption_service()
            value = row.config_value
            if row.is_encrypted:
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
                    value = {}
            if isinstance(value, dict):
                token = value.get("token")
                if isinstance(token, str) and token.strip():
                    return token.strip()

        if is_sandbox():
            platform_token = os.environ.get("VERCEL_PLATFORM_TOKEN", "").strip()
            if platform_token:
                return platform_token

        raise RuntimeError(
            "Vercel token not configured. "
            "Please configure it in Settings → Deploy or use the deploy button in the artifact panel."
        )
