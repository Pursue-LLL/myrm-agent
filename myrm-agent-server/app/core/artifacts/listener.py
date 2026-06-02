"""Artifact event listener.

[INPUT]
- app.database.connection::get_session (POS: Database session)
- app.database.models.artifact::Artifact (POS: Artifact models)

[OUTPUT]
- persist_artifact_event: function — Persist artifact registry event to DB

[POS]
Listens to ArtifactRegistry events and persists them to the database.
"""

import logging
import uuid

from myrm_agent_harness.agent.artifacts.registry import GeneratedFile
from myrm_agent_harness.agent.artifacts.vault import VAULT_PREFIX, ArtifactVault
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.artifact import Artifact, ArtifactVersion

logger = logging.getLogger(__name__)


async def persist_artifact_event(
    db: AsyncSession,
    files: list[GeneratedFile],
    workspace_root: str,
    chat_id: str | None = None,
    owner_id: str | None = None,
    tenant_id: str | None = None,
) -> None:
    """Persist generated files from ArtifactRegistry into the Artifact database models."""
    logger.warning(
        f" [persist_artifact_event] Called with {len(files)} files for chat_id={chat_id}"
    )
    if not files:
        return

    vault = ArtifactVault(workspace_root)

    for file in files:
        # Check if the file is a vault URI or a local file path
        if file.path.startswith(VAULT_PREFIX):
            vault_uri = file.path
            meta = vault.get_meta(vault_uri)
            if not meta:
                logger.warning(
                    f"Vault meta not found for {vault_uri}, skipping persistence."
                )
                continue

            filename = meta.filename
            sha256_hash = getattr(meta, "sha256_hash", "")
            description = meta.description
        else:
            # If it's a raw file path, we need to put it into the vault first to get a hash and URI
            try:
                import os

                # Check if it's already an absolute path
                if os.path.isabs(file.path):
                    file_path = file.path
                else:
                    # In test environments, the files might be written to the workspace_root/chat_id/
                    # Try a few common path resolutions
                    possible_paths = [
                        file.path,  # As-is (might be absolute)
                        os.path.join(
                            workspace_root, file.path
                        ),  # Relative to workspace root
                    ]

                    # Try to find which chat this belongs to if the path includes sandboxes/
                    if chat_id:
                        possible_paths.append(
                            os.path.join(
                                workspace_root, f"sandboxes/{chat_id}", file.path
                            )
                        )
                        possible_paths.append(
                            os.path.join(workspace_root, chat_id, file.path)
                        )

                        # Also check the parent directory of workspace_root just in case
                        workspace_parent = os.path.dirname(workspace_root)
                        possible_paths.append(
                            os.path.join(workspace_parent, f"chat_{chat_id}", file.path)
                        )

                    # Also try resolving through the executor's workspace if possible
                    try:
                        from myrm_agent_harness.toolkits.code_execution.executors.base import (
                            get_executor,
                        )

                        executor = get_executor()
                        if (
                            executor
                            and hasattr(executor, "_current_workspace")
                            and executor._current_workspace
                        ):
                            possible_paths.append(
                                os.path.join(
                                    str(executor._current_workspace), file.path
                                )
                            )
                    except Exception:
                        pass

                    file_path = next(
                        (p for p in possible_paths if os.path.exists(p)), None
                    )

                    if not file_path:
                        # As a fallback, try a recursive find from workspace root
                        for root, _, filenames in os.walk(workspace_root):
                            if os.path.basename(file.path) in filenames:
                                file_path = os.path.join(
                                    root, os.path.basename(file.path)
                                )
                                break

                if not file_path or not os.path.exists(file_path):
                    logger.warning(
                        f"Generated file {file.path} not found on disk, skipping."
                    )
                    continue

                filename = os.path.basename(file.path)
                vault_uri = vault.put_file(
                    file_path=file_path,
                    filename=filename,
                    description="Auto-persisted from registry",
                )

                meta = vault.get_meta(vault_uri)
                sha256_hash = getattr(meta, "sha256_hash", "")
                description = meta.description
            except Exception as e:
                logger.error(f"Failed to persist raw file {file.path} to vault: {e}")
                continue

        # Check if an artifact with this name already exists in this chat
        stmt = select(Artifact).where(
            Artifact.name == filename,
            Artifact.chat_id == chat_id,
            Artifact.is_deleted.is_(False),
        )
        result = await db.execute(stmt)
        artifact = result.scalars().first()

        if not artifact:
            # Create new artifact
            artifact = Artifact(
                id=str(uuid.uuid4()),
                tenant_id=tenant_id,
                owner_id=owner_id,
                chat_id=chat_id,
                name=filename,
                description=description,
            )
            db.add(artifact)
            await db.flush()  # Get the ID

        # Create new version
        version = ArtifactVersion(
            id=str(uuid.uuid4()),
            artifact_id=artifact.id,
            vault_uri=vault_uri,
            sha256_hash=sha256_hash,
            creator_id="agent",  # Assuming it's generated by the agent
            commit_message="Auto-saved by artifact listener",
        )
        db.add(version)

    try:
        await db.commit()
        logger.warning(
            f" [persist_artifact_event] Successfully persisted {len(files)} artifacts to database."
        )
    except Exception as e:
        await db.rollback()
        logger.warning(
            f" [persist_artifact_event] Failed to commit artifact persistence: {e}"
        )
