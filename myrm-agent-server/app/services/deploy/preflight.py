"""Deploy preflight evaluation for artifact publishing.

[INPUT]
- app.services.deploy.deploy_packager::collect_deploy_files, validate_deploy_payload

[OUTPUT]
- resolve_artifact_deploy_files: load vault payload for an artifact
- evaluate_deploy_preflight: structured deployability result

[POS]
Shared deploy packaging checks used by deploy API and frontend preflight gate.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.artifacts.listener import ensure_artifact_for_deploy, resolve_sandbox_file_path
from app.database.models.artifact import Artifact
from app.services.deploy.deploy_packager import DeployFile, collect_deploy_files, validate_deploy_payload

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


def _vault_object_path(vault: ArtifactVault, vault_uri: str) -> Path:
    obj_id = vault_uri[len("vault://") :] if vault_uri.startswith("vault://") else vault_uri
    return vault.get_object_path(obj_id)


async def resolve_artifact_deploy_files(
    db: AsyncSession,
    artifact_id: str,
    workspace_root: str,
) -> tuple[Artifact, dict[str, DeployFile]]:
    """Load artifact and collect files that would be sent to Vercel."""
    artifact = await ensure_artifact_for_deploy(db, artifact_id, workspace_root)
    if not artifact.versions:
        raise ValueError("NO_VERSIONS")

    latest_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
    vault = ArtifactVault(workspace_root)
    obj_path = _vault_object_path(vault, latest_version.vault_uri)
    asset_root: Path | None = None
    if artifact.chat_id and artifact.name:
        resolved = resolve_sandbox_file_path(artifact.name, workspace_root, artifact.chat_id)
        if resolved:
            asset_root = Path(resolved).parent
    files_to_deploy = collect_deploy_files(
        obj_path,
        asset_root=asset_root,
        entry_name_hint=artifact.name,
    )
    return artifact, files_to_deploy


def evaluate_deploy_preflight(files: dict[str, DeployFile]) -> DeployPreflightResult:
    """Return whether the collected payload can be deployed as static HTML."""
    if not files:
        return DeployPreflightResult(
            deployable=False,
            reason="EMPTY_PAYLOAD",
            message="No deployable files found for this artifact.",
            hint=None,
        )
    try:
        validate_deploy_payload(files)
    except ValueError as exc:
        msg = str(exc)
        html_entries = [name for name in files if name.lower().endswith((".html", ".htm"))]
        code_entries = [
            name
            for name in files
            if name.lower().endswith((".tsx", ".ts", ".jsx", ".js", ".vue", ".svelte"))
        ]
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
