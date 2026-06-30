"""Deploy preflight evaluation for artifact publishing.

[INPUT]
- app.services.deploy.deploy_packager::collect_deploy_files, validate_deploy_payload
- app.services.deploy.artifact_files::resolve_artifact_deploy_files (POS: vault file collection)

[OUTPUT]
- evaluate_deploy_preflight: structured deployability result
- run_deploy_preflight: full preflight for an artifact id

[POS]
Shared deploy packaging checks used by deploy API and frontend preflight gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.hosting.artifact_files import resolve_artifact_deploy_files
from app.services.hosting.packager import PublishFile, validate_publish_payload

logger = logging.getLogger(__name__)

DeployPreflightReason = Literal[
    "OK",
    "NO_VERSIONS",
    "EMPTY_PAYLOAD",
    "REQUIRES_HTML_ENTRY",
    "CODE_REQUIRES_HTML_ARTIFACT",
    "PACKAGING_ERROR",
]


@dataclass(frozen=True)
class DeployPreflightResult:
    deployable: bool
    reason: DeployPreflightReason
    message: str
    hint: str | None = None


def evaluate_deploy_preflight(files: dict[str, PublishFile]) -> DeployPreflightResult:
    """Return whether the collected payload can be deployed as static HTML."""
    if not files:
        return DeployPreflightResult(
            deployable=False,
            reason="EMPTY_PAYLOAD",
            message="No deployable files found for this artifact.",
            hint=None,
        )
    try:
        validate_publish_payload(files)
    except ValueError as exc:
        msg = str(exc)
        html_entries = [name for name in files if name.lower().endswith((".html", ".htm"))]
        code_entries = [name for name in files if name.lower().endswith((".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte"))]
        if code_entries and not html_entries:
            return DeployPreflightResult(
                deployable=False,
                reason="CODE_REQUIRES_HTML_ARTIFACT",
                message="React/code artifacts must be exported as a complete index.html before deploy.",
                hint="Ask the agent to output a full HTML document artifact (type html), then deploy.",
            )
        return DeployPreflightResult(
            deployable=False,
            reason="REQUIRES_HTML_ENTRY",
            message=msg,
            hint="Deploy requires index.html or a single HTML file in the artifact.",
        )
    return DeployPreflightResult(
        deployable=True,
        reason="OK",
        message="Artifact is ready to deploy.",
        hint=None,
    )


async def run_deploy_preflight(
    db: AsyncSession,
    artifact_id: str,
    workspace_root: str,
) -> DeployPreflightResult:
    """Full preflight: resolve files then evaluate deployability."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database.models.artifact import Artifact

    row = await db.execute(
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    )
    existing = row.scalars().first()
    if existing is not None and not existing.versions:
        return DeployPreflightResult(
            deployable=False,
            reason="NO_VERSIONS",
            message="Artifact has no versions to deploy.",
            hint=None,
        )

    try:
        _, files = await resolve_artifact_deploy_files(db, artifact_id, workspace_root)
    except LookupError:
        return DeployPreflightResult(
            deployable=False,
            reason="PACKAGING_ERROR",
            message="Artifact not found.",
            hint=None,
        )
    except FileNotFoundError:
        return DeployPreflightResult(
            deployable=False,
            reason="PACKAGING_ERROR",
            message="Artifact files are missing on disk.",
            hint=None,
        )
    except ValueError as exc:
        if str(exc) == "NO_VERSIONS":
            return DeployPreflightResult(
                deployable=False,
                reason="NO_VERSIONS",
                message="Artifact has no versions to deploy.",
                hint=None,
            )
        logger.warning("Deploy preflight packaging failed for %s: %s", artifact_id, exc)
        return DeployPreflightResult(
            deployable=False,
            reason="PACKAGING_ERROR",
            message=str(exc),
            hint=None,
        )
    except Exception as exc:
        logger.error("Deploy preflight failed for %s: %s", artifact_id, exc)
        return DeployPreflightResult(
            deployable=False,
            reason="PACKAGING_ERROR",
            message="Failed to read artifact files for deploy.",
            hint=None,
        )
    return evaluate_deploy_preflight(files)
