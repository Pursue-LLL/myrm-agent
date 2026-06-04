"""Resolve artifact vault content for public share viewing.

[INPUT]
- ArtifactVault, Artifact ORM models

[OUTPUT]
- resolve_shareable_version_path: Path + media metadata

[POS]
Server-side helper for signed public artifact preview routes.
"""

from __future__ import annotations

import mimetypes
from dataclasses import dataclass
from pathlib import Path

from myrm_agent_harness.agent.artifacts.vault import ArtifactVault
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.artifact import Artifact, ArtifactVersion
from app.services.artifacts.share_token import is_shareable_artifact_name


@dataclass(frozen=True)
class ShareableArtifactContent:
    path: Path
    filename: str
    media_type: str
    artifact_id: str
    version_id: str


def _guess_media_type(filename: str) -> str:
    guessed, _ = mimetypes.guess_type(filename)
    if guessed:
        return guessed
    lower = filename.lower()
    if lower.endswith(".pdf"):
        return "application/pdf"
    if lower.endswith((".md", ".markdown")):
        return "text/markdown; charset=utf-8"
    if lower.endswith(".txt"):
        return "text/plain; charset=utf-8"
    return "text/html; charset=utf-8"


async def resolve_shareable_version(
    db: AsyncSession,
    artifact_id: str,
    version_id: str,
    workspace_root: str,
) -> ShareableArtifactContent:
    """Load a specific artifact version for inline public viewing."""
    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    )
    result = await db.execute(stmt)
    artifact = result.scalars().first()
    if not artifact:
        raise LookupError("Artifact not found")

    if not is_shareable_artifact_name(artifact.name):
        raise PermissionError("Artifact type is not allowed for public share")

    version: ArtifactVersion | None = next((v for v in artifact.versions if v.id == version_id), None)
    if version is None:
        raise LookupError("Artifact version not found")

    vault = ArtifactVault(workspace_root)
    obj_id = version.vault_uri[len("vault://") :] if version.vault_uri.startswith("vault://") else version.vault_uri
    obj_path = vault.get_object_path(obj_id)
    if not obj_path.exists():
        raise FileNotFoundError("Artifact content not found on disk")

    meta = vault.get_meta(version.vault_uri)
    filename = meta.filename if meta and meta.filename else artifact.name
    media_type = meta.content_type if meta and meta.content_type else _guess_media_type(filename)

    return ShareableArtifactContent(
        path=obj_path,
        filename=filename,
        media_type=media_type,
        artifact_id=artifact.id,
        version_id=version.id,
    )
