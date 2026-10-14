"""Workspace cleanup service for chat deletion.

Cleans up workspace resources when a user deletes a chat:
1. Local workspace directory (via WorkspaceService)
2. Oversized temporary objects in the ArtifactVault

Several chats are cleaned in one call so the shared vault is scanned once, not once per chat.
"""

import asyncio
import logging
from collections.abc import Sequence
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config.settings import settings

logger = logging.getLogger(__name__)


def _purge_vault_objects(harness_dir: Path, chat_ids: Sequence[str]) -> int:
    """Delete the vault objects of ``chat_ids`` and return how many went.

    Walks and unlinks files, so it blocks; callers run it in a worker thread.
    """
    from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

    purged_total = 0
    for chat_id in chat_ids:
        session_workspace = harness_dir / "workspaces" / f"chat_{chat_id}"
        if session_workspace.exists():
            purged_total += ArtifactVault(str(session_workspace)).purge_all()

    # The shared root holds task-tagged objects of every chat; the whole batch is scanned once.
    purged_total += ArtifactVault(str(harness_dir)).purge_by_task_ids(chat_ids)
    return purged_total


class WorkspaceCleanupService:
    """Workspace cleanup service."""

    @staticmethod
    async def cleanup_chat_workspace(chat_id: str) -> dict[str, bool]:
        """Clean up workspace resources associated with a chat.

        Args:
            chat_id: Chat ID.

        Returns:
            Cleanup result dict with per-resource status.
        """
        return await WorkspaceCleanupService.cleanup_chat_workspaces([chat_id])

    @staticmethod
    async def cleanup_chat_workspaces(chat_ids: Sequence[str]) -> dict[str, bool]:
        """Clean up the workspace resources of several chats, scanning the shared vault once.

        Args:
            chat_ids: Chat IDs.

        Returns:
            Cleanup result dict with per-resource status; a resource is True only if it succeeded for every chat.
        """
        if not chat_ids:
            return {"storage_workspace": True, "artifact_vault": True}
        storage_cleaned = True
        for chat_id in chat_ids:
            storage_cleaned = await WorkspaceCleanupService._cleanup_storage_workspace(chat_id) and storage_cleaned
        return {
            "storage_workspace": storage_cleaned,
            "artifact_vault": await WorkspaceCleanupService._cleanup_artifact_vault(chat_ids),
        }

    @staticmethod
    async def _cleanup_artifact_vault(chat_ids: Sequence[str]) -> bool:
        """Clean up oversized temporary objects produced in ArtifactVault for these chats."""
        try:
            purged_total = await asyncio.to_thread(_purge_vault_objects, Path(settings.database.harness_dir), chat_ids)
            if purged_total > 0:
                logger.info("Cleaned %d vault artifacts (chats=%d)", purged_total, len(chat_ids))
            return True
        except Exception as e:
            logger.warning("Failed to cleanup artifact vault for %d chats: %s", len(chat_ids), e)
            return False

    @staticmethod
    async def _cleanup_storage_workspace(chat_id: str) -> bool:
        """Clean up workspace directory by session_id lookup.

        Composes session_id from chat_id and deletes the workspace.
        """
        try:
            workspace_service = create_workspace_service(root_dir=Path(settings.database.harness_dir))
            session_id = f"chat_{chat_id}"

            workspace = await workspace_service.find_by_session_id(session_id)
            if not workspace:
                logger.debug("No workspace found for session=%s", session_id)
                return True

            deleted = await workspace_service.delete(workspace)
            if deleted:
                logger.info("Cleaned workspace: %s (chat=%s)", workspace.id, chat_id)
            return True

        except Exception as e:
            logger.error("Failed to cleanup storage workspace (chat=%s): %s", chat_id, e)
            return False


async def cleanup_chat_workspace(chat_id: str) -> dict[str, bool]:
    """Convenience function for chat workspace cleanup."""
    return await WorkspaceCleanupService.cleanup_chat_workspace(chat_id)


async def cleanup_chat_workspaces(chat_ids: Sequence[str]) -> dict[str, bool]:
    """Convenience function for cleaning the workspaces of several chats at once."""
    return await WorkspaceCleanupService.cleanup_chat_workspaces(chat_ids)
