"""Agent-facing deployment service implementing DeployBackend.

[INPUT]
- app.services.deploy.protocols::DeployBackend
- app.services.deploy.credentials::resolve_vercel_token
- app.services.deploy.preflight::run_deploy_preflight
- app.services.deploy.vercel_artifact_deploy::execute_vercel_artifact_deploy

[OUTPUT]
- AgentDeployService: concrete DeployBackend for tool_setup.py

[POS]
Agent deploy_artifact 工具的 DeployBackend 实现；部署执行委托 vercel_artifact_deploy。
"""

from __future__ import annotations

from app.services.deploy.types import DeployResult


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
        """Execute Vercel deployment via the shared executor used by deploy_api."""
        from app.database.connection import get_session
        from app.services.deploy.credentials import resolve_vercel_token
        from app.services.deploy.vercel_artifact_deploy import execute_vercel_artifact_deploy

        async with get_session() as db:
            try:
                vercel_token = await resolve_vercel_token(db)
            except RuntimeError as exc:
                return DeployResult(
                    success=False,
                    url="",
                    deployment_id="",
                    project_id="",
                    status="TOKEN_MISSING",
                    error=str(exc),
                )

            return await execute_vercel_artifact_deploy(
                db,
                artifact_id,
                self._workspace_root,
                vercel_token=vercel_token,
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
