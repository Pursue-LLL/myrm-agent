"""Artifact event listener.

[INPUT]
- app.database.connection::get_session (POS: Database session)
- app.database.models.artifact::Artifact (POS: Artifact models)

[OUTPUT]
- upsert_processor_artifact: function — Upsert Artifact(id=file_id) + Version
- ensure_artifact_for_deploy: function — Load or JIT-prepare deploy artifact
- persist_artifact_event: function — Persist harness registry batch (legacy)

[POS]
Persists chat artifacts for deploy/hydrate; Artifact.id matches SSE file_id.
"""

from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

from myrm_agent_harness.agent.artifacts.registry import GeneratedFile
from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion

logger = logging.getLogger(__name__)

_WALK_SKIP_DIRS: frozenset[str] = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    ".pytest_cache", ".mypy_cache", ".ruff_cache",
    "dist", "build", ".next", ".nuxt", "target", "out",
})


def resolve_sandbox_file_path(
    file_path: str,
    workspace_root: str,
    chat_id: str | None = None,
) -> str | None:
    """Resolve a sandbox-relative or absolute path to an on-disk file."""
    if os.path.isabs(file_path) and os.path.exists(file_path):
        return file_path

    possible_paths = [
        file_path,
        os.path.join(workspace_root, file_path),
    ]
    if chat_id:
        possible_paths.extend(
            [
                os.path.join(workspace_root, f"sandboxes/{chat_id}", file_path),
                os.path.join(workspace_root, chat_id, file_path),
                os.path.join(os.path.dirname(workspace_root), f"chat_{chat_id}", file_path),
            ]
        )

    try:
        from myrm_agent_harness.toolkits.code_execution.executors.base import get_executor

        executor = get_executor()
        if executor and hasattr(executor, "_current_workspace") and executor._current_workspace:
            possible_paths.append(os.path.join(str(executor._current_workspace), file_path))
    except Exception:
        pass

    resolved = next((p for p in possible_paths if os.path.exists(p)), None)
    if resolved:
        return resolved

    basename = os.path.basename(file_path)
    for root, dirs, filenames in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d not in _WALK_SKIP_DIRS]
        if basename in filenames:
            return os.path.join(root, basename)
    return None


async def upsert_processor_artifact(
    db: AsyncSession,
    *,
    file_id: str,
    filename: str,
    sandbox_path: str,
    workspace_root: str,
    chat_id: str | None = None,
    owner_id: str | None = None,
    tenant_id: str | None = None,
    physical_path: str | None = None,
) -> str:
    """Upsert deploy DB row keyed by storage file_id; returns latest version id."""
    resolved_path = physical_path or resolve_sandbox_file_path(sandbox_path, workspace_root, chat_id)
    if not resolved_path:
        raise FileNotFoundError(f"Artifact file not found on disk: {sandbox_path}")

    vault = ArtifactVault(workspace_root)
    vault_uri = vault.put_file(
        file_path=resolved_path,
        filename=filename,
        description="Persisted from chat artifact processor",
    )
    meta = vault.get_meta(vault_uri)
    if not meta:
        raise FileNotFoundError(f"Vault meta missing after put: {vault_uri}")

    sha256_hash = getattr(meta, "sha256_hash", "") or ""
    description = meta.description

    stmt = select(Artifact).where(Artifact.id == file_id, Artifact.is_deleted.is_(False))
    artifact = (await db.execute(stmt)).scalars().first()

    if not artifact:
        artifact = Artifact(
            id=file_id,
            tenant_id=tenant_id,
            owner_id=owner_id,
            chat_id=chat_id,
            name=filename,
            description=description,
        )
        db.add(artifact)
        await db.flush()
    else:
        artifact.name = filename
        if description:
            artifact.description = description

    version = ArtifactVersion(
        id=str(uuid.uuid4()),
        artifact_id=artifact.id,
        vault_uri=vault_uri,
        sha256_hash=sha256_hash,
        creator_id="agent",
        commit_message="Auto-saved from chat artifact",
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    logger.info("Upserted deploy artifact %s version %s", file_id, version.id)
    return version.id


async def ensure_artifact_for_deploy(
    db: AsyncSession,
    artifact_id: str,
    workspace_root: str,
) -> Artifact:
    """Load Artifact by file_id or JIT-upsert from FilesService metadata."""
    from sqlalchemy.orm import selectinload

    from app.core.storage import FilesService

    stmt = (
        select(Artifact)
        .options(selectinload(Artifact.versions))
        .where(Artifact.id == artifact_id, Artifact.is_deleted.is_(False))
    )
    artifact = (await db.execute(stmt)).scalars().first()
    if artifact and artifact.versions:
        return artifact

    files_svc = FilesService()
    file_record = await files_svc.get_file_by_id(artifact_id)
    if not file_record:
        raise LookupError(f"Artifact not found: {artifact_id}")

    physical_path: str | None = None
    sandbox_path = file_record.filename
    content = await files_svc.get_file_content_by_path(file_record.storage_path)
    if content is not None:
        import tempfile

        suffix = Path(file_record.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            physical_path = tmp.name
    elif file_record.source_chat_id:
        rel = file_record.storage_path
        if rel.startswith(f"sandboxes/{file_record.source_chat_id}/"):
            sandbox_path = rel.split("/", 2)[-1]

    try:
        await upsert_processor_artifact(
            db,
            file_id=artifact_id,
            filename=file_record.filename,
            sandbox_path=sandbox_path,
            workspace_root=workspace_root,
            chat_id=file_record.source_chat_id,
            physical_path=physical_path,
        )
    finally:
        if physical_path:
            try:
                os.remove(physical_path)
            except OSError:
                pass

    result = await db.execute(stmt)
    loaded = result.scalars().first()
    if not loaded or not loaded.versions:
        raise LookupError(f"Failed to prepare artifact for deploy: {artifact_id}")
    return loaded


async def persist_artifact_event(
    db: AsyncSession,
    files: list[GeneratedFile],
    workspace_root: str,
    chat_id: str | None = None,
    owner_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """Persist generated files from ArtifactRegistry into the Artifact database models."""
    if not files:
        return

    vault = ArtifactVault(workspace_root)

    for file in files:
        if file.path.startswith(VAULT_PREFIX):
            vault_uri = file.path
            meta = vault.get_meta(vault_uri)
            if not meta:
                logger.warning("Vault meta not found for %s, skipping persistence.", vault_uri)
                continue

            filename = meta.filename
            sha256_hash = getattr(meta, "sha256_hash", "")
            description = meta.description
        else:
            try:
                file_path = resolve_sandbox_file_path(file.path, workspace_root, chat_id)
                if not file_path:
                    logger.warning("Generated file %s not found on disk, skipping.", file.path)
                    continue

                filename = os.path.basename(file_path)
                vault_uri = vault.put_file(
                    file_path=file_path,
                    filename=filename,
                    description="Auto-persisted from registry",
                )

                meta = vault.get_meta(vault_uri)
                sha256_hash = getattr(meta, "sha256_hash", "")
                description = meta.description
            except Exception as e:
                logger.error("Failed to persist raw file %s to vault: %s", file.path, e)
                continue

        stmt = select(Artifact).where(
            Artifact.name == filename,
            Artifact.chat_id == chat_id,
            Artifact.is_deleted.is_(False),
        )
        artifact = (await db.execute(stmt)).scalars().first()

        if not artifact:
            artifact = Artifact(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                owner_id=owner_id,
                chat_id=chat_id,
                name=filename,
                description=description,
            )
            db.add(artifact)
            await db.flush()

        version = ArtifactVersion(
            id=str(uuid.uuid4()),
            artifact_id=artifact.id,
            vault_uri=vault_uri,
            sha256_hash=sha256_hash,
            creator_id="agent",
            commit_message="Auto-saved by artifact listener",
        )
        db.add(version)

    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        logger.warning("Failed to commit artifact persistence: %s", e)
