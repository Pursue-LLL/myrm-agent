"""Workspace cleanup service for chat deletion.

Cleans up workspace resources when a user deletes a chat:
1. Local workspace directory (via WorkspaceService)
2. Container session directory (via ContainerManager)
"""

import logging
from pathlib import Path

from myrm_agent_harness.toolkits.code_execution import create_workspace_service

from app.config.settings import settings

logger = logging.getLogger(__name__)


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
        results: dict[str, bool] = {
            "storage_workspace": False,
            "container_session": False,
        }

        results["storage_workspace"] = await WorkspaceCleanupService._cleanup_storage_workspace(chat_id)

        results["container_session"] = await WorkspaceCleanupService._cleanup_container_session(chat_id)

        return results

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

    @staticmethod
    async def _cleanup_container_session(chat_id: str) -> bool:
        """Clean up container session directory."""
        try:
            from myrm_agent_harness.toolkits.code_execution.container.manager import (
                get_container_id_for_session,
                get_container_manager,
            )

            manager = get_container_manager()

            session_id = f"chat_{chat_id}"
            container_id = await get_container_id_for_session(manager, session_id)
            if not container_id:
                logger.debug("No container session to cleanup (session=%s)", session_id)
                return True

            await manager.release_container(container_id, session_id)
            logger.info(
                "Cleaned container session (session=%s, container=%s)",
                session_id,
                container_id[:12],
            )
            return True

        except Exception as e:
            logger.error("Failed to cleanup container session (chat=%s): %s", chat_id, e)
            return False


async def cleanup_chat_workspace(chat_id: str) -> dict[str, bool]:
    """Convenience function for chat workspace cleanup."""
    return await WorkspaceCleanupService.cleanup_chat_workspace(chat_id)
