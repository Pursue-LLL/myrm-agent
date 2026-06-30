"""Vercel hosting provider.

[POS] HostingProvider implementation for Vercel static deployments.
"""

from __future__ import annotations

import logging

from app.services.hosting.packager import PublishFile
from app.services.hosting.types import HostingTarget, PublicationResult
from app.services.hosting.vercel_client import VercelClient

logger = logging.getLogger(__name__)


def sanitize_vercel_project_name(artifact_name: str, artifact_id: str) -> str:
    project_name = "".join(c if c.isalnum() or c == "-" else "-" for c in artifact_name.lower())
    if not project_name:
        project_name = f"myrm-artifact-{artifact_id[:8]}"
    return project_name


class VercelHostingProvider:
    provider_type = "vercel"

    async def test_connection(self, target: HostingTarget, credentials: dict[str, object]) -> tuple[bool, str]:
        token = credentials.get("token")
        if not isinstance(token, str) or not token.strip():
            return False, "Vercel token is required."
        return True, "Vercel credentials configured."

    async def publish(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        artifact_id: str,
        artifact_name: str,
        files: dict[str, PublishFile],
        existing_project_ref: str | None,
    ) -> PublicationResult:
        token = credentials.get("token")
        if not isinstance(token, str) or not token.strip():
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref="",
                status="ERROR",
                error="Vercel token is required.",
            )
        client = VercelClient(token=token.strip())
        project_name = sanitize_vercel_project_name(artifact_name, artifact_id)
        try:
            deploy_result = await client.deploy(
                project_name=project_name,
                files=files,
                project_id=existing_project_ref,
            )
        except Exception as exc:
            logger.error("Vercel publish failed for artifact %s: %s", artifact_id, exc)
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref=existing_project_ref or "",
                status="ERROR",
                error=str(exc),
            )
        return PublicationResult(
            success=True,
            url=str(deploy_result.get("url", "")),
            publication_id=str(deploy_result.get("deployment_id", "")),
            project_ref=str(deploy_result.get("project_id", "")),
            status=str(deploy_result.get("status", "READY")),
        )

    async def poll_status(
        self,
        *,
        target: HostingTarget,
        credentials: dict[str, object],
        publication_id: str,
    ) -> dict[str, str]:
        token = credentials.get("token")
        if not isinstance(token, str) or not token.strip():
            return {"status": "ERROR", "error": "Missing Vercel token"}
        client = VercelClient(token=token.strip())
        data = await client.get_deployment_status(publication_id)
        return {
            "id": str(data.get("id", publication_id)),
            "url": str(data.get("url", "")),
            "status": str(data.get("status", "UNKNOWN")),
        }
