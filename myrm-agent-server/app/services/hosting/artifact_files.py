"""Resolve artifact vault payloads into deployable file maps.

[INPUT]
- app.core.artifacts.listener::ensure_artifact_for_deploy, resolve_sandbox_file_path
- app.services.hosting.packager::collect_publish_files
- myrm_agent_harness.agent.artifacts.vault::ArtifactVault (POS: sandbox artifact storage)

[OUTPUT]
- resolve_artifact_deploy_files: Artifact + file map for deploy and share bundles

[POS]
Shared artifact file collection for Vercel deploy, deploy preflight, and public share bundles.
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.artifacts.listener import ensure_artifact_for_deploy, resolve_sandbox_file_path
from app.database.models.artifact import Artifact
from app.services.hosting.packager import PublishFile, collect_publish_files


def _vault_object_path(vault: ArtifactVault, vault_uri: str) -> Path:
    obj_id = vault_uri[len("vault://") :] if vault_uri.startswith("vault://") else vault_uri
    return vault.get_object_path(obj_id)


async def resolve_artifact_deploy_files(
    db: AsyncSession,
    artifact_id: str,
    workspace_root: str,
    *,
    version_id: str | None = None,
) -> tuple[Artifact, dict[str, PublishFile]]:
    """Load artifact and collect static files (vault object + sandbox asset_root).

    When *version_id* is provided the exact version is resolved (used by share
    bundle re-materialization to honour the pinned version in the JWT token).
    Otherwise the latest version is used (deploy / preflight path).
    """
    artifact = await ensure_artifact_for_deploy(db, artifact_id, workspace_root)
    if not artifact.versions:
        raise ValueError("NO_VERSIONS")

    if version_id is not None:
        target_version = next(
            (v for v in artifact.versions if v.id == version_id), None
        )
        if target_version is None:
            raise LookupError(f"Artifact version {version_id} not found")
    else:
        target_version = sorted(artifact.versions, key=lambda v: v.created_at, reverse=True)[0]
    vault = ArtifactVault(workspace_root)
    obj_path = _vault_object_path(vault, target_version.vault_uri)
    asset_root: Path | None = None
    if artifact.chat_id and artifact.name:
        resolved = resolve_sandbox_file_path(artifact.name, workspace_root, artifact.chat_id)
        if resolved:
            asset_root = Path(resolved).parent
    files_to_deploy = collect_publish_files(
        obj_path,
        asset_root=asset_root,
        entry_name_hint=artifact.name,
    )
    return artifact, files_to_deploy
