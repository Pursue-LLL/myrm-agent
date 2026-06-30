"""Orchestrate artifact publication to hosting targets.

[POS] Coordinate preflight, publish, and persistence across hosting providers.

[INPUT]
- app.services.hosting.registry (POS: provider lookup by target type)

[OUTPUT]
- publish_artifact_to_target: end-to-end publication orchestration
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hosting.artifact_files import resolve_artifact_deploy_files
from app.services.hosting.credentials import resolve_target_credentials
from app.services.hosting.preflight import evaluate_deploy_preflight
from app.services.hosting.publication_store import get_publication, upsert_publication
from app.services.hosting.registry import get_hosting_provider
from app.services.hosting.targets import get_hosting_target
from app.services.hosting.types import PublicationResult

logger = logging.getLogger(__name__)


async def publish_artifact_to_target(
    db: AsyncSession,
    artifact_id: str,
    workspace_root: str,
    *,
    hosting_target_id: str,
    request_token: str = "",
) -> PublicationResult:
    target = await get_hosting_target(db, hosting_target_id)
    if target is None:
        return PublicationResult(
            success=False,
            url="",
            publication_id="",
            project_ref="",
            status="ERROR",
            error="Hosting target not found.",
        )

    try:
        artifact, files = await resolve_artifact_deploy_files(db, artifact_id, workspace_root)
    except LookupError:
        return PublicationResult(
            success=False,
            url="",
            publication_id="",
            project_ref="",
            status="ERROR",
            error="Artifact not found.",
        )
    except ValueError as exc:
        if str(exc) == "NO_VERSIONS":
            return PublicationResult(
                success=False,
                url="",
                publication_id="",
                project_ref="",
                status="PREFLIGHT_FAILED",
                error="Artifact has no versions to publish.",
            )
        raise

    check = evaluate_deploy_preflight(files)
    if not check.deployable:
        return PublicationResult(
            success=False,
            url="",
            publication_id="",
            project_ref="",
            status="PREFLIGHT_FAILED",
            error=check.message,
        )

    latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
    existing = await get_publication(db, artifact_id, hosting_target_id)
    existing_project_ref = existing.publication_project_ref if existing else None

    try:
        credentials = await resolve_target_credentials(db, hosting_target_id, request_token=request_token)
    except RuntimeError as exc:
        return PublicationResult(
            success=False,
            url="",
            publication_id="",
            project_ref=existing_project_ref or "",
            status="ERROR",
            error=str(exc),
        )

    provider = get_hosting_provider(target.provider_type)
    result = await provider.publish(
        target=target,
        credentials=credentials,
        artifact_id=artifact_id,
        artifact_name=artifact.name,
        files=files,
        existing_project_ref=existing_project_ref,
    )

    row = await upsert_publication(
        db,
        artifact_id=artifact_id,
        hosting_target_id=hosting_target_id,
        publication_url=result.url if result.success else existing.publication_url if existing else None,
        publication_status=result.status,
        publication_project_ref=result.project_ref or existing_project_ref,
        publication_version_id=latest_version.id if result.success else (
            existing.publication_version_id if existing else None
        ),
    )

    return PublicationResult(
        success=result.success,
        url=result.url,
        publication_id=result.publication_id,
        project_ref=result.project_ref,
        status=result.status,
        error=result.error,
        latest_version_id=latest_version.id if result.success else None,
        publication_row_id=row.id,
    )
