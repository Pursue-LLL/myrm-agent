"""Sync channel chat workspace from topic binding into chat SSOT.

[INPUT]
- app.channels.types::TopicContext
- app.database.dto::ChatDTO
- app.services.chat.effective_workspace::resolve_effective_chat_workspace
- app.services.workspace.file_watch_service::resolve_watchable_workspace_path

[OUTPUT]
- sync_channel_chat_workspace: apply or clear topic project/path on chat.project_id or workspace_dir
- _apply_chat_workspace_updates: idempotent chat SSOT field writer
- ChannelWorkspaceSyncError: fail-loud when topic declares workspace but path unavailable

[POS]
Channel executor helper: bridge topic-level vault binding to existing chat workspace SSOT.
"""

from __future__ import annotations

import logging

from app.channels.types import TopicContext
from app.database.dto import ChatDTO

logger = logging.getLogger(__name__)


class ChannelWorkspaceSyncError(Exception):
    """Topic workspace binding cannot be applied to the channel chat."""


def topic_declares_workspace(topic_context: TopicContext | None) -> bool:
    if topic_context is None:
        return False
    return bool(topic_context.project_id or topic_context.authorized_path)


async def _apply_chat_workspace_updates(
    chat: ChatDTO,
    updates: dict[str, object],
) -> ChatDTO:
    if chat.project_id == updates.get("project_id") and chat.workspace_dir == updates.get("workspace_dir"):
        return chat

    from app.services.chat.chat_service import ChatService

    await ChatService.update_chat_fields(chat.id, updates)
    logger.info(
        "Channel chat workspace synced: chat_id=%s project_id=%s workspace_dir=%s",
        chat.id,
        updates.get("project_id"),
        updates.get("workspace_dir"),
    )
    return chat.model_copy(update=updates)


async def sync_channel_chat_workspace(
    chat: ChatDTO,
    topic_context: TopicContext | None,
) -> ChatDTO:
    """Apply topic workspace binding to chat SSOT fields before Agent execution."""
    if not topic_declares_workspace(topic_context):
        if chat.project_id is None and chat.workspace_dir is None:
            return chat
        return await _apply_chat_workspace_updates(
            chat,
            {"project_id": None, "workspace_dir": None},
        )
    assert topic_context is not None

    updates: dict[str, object] = {}

    if topic_context.project_id:
        from app.services.project.project_service import ProjectService

        project = await ProjectService.get_project(topic_context.project_id)
        if project is None or not project.workspace_path:
            raise ChannelWorkspaceSyncError(f"Project workspace is unavailable: {topic_context.project_id}")
        updates["project_id"] = topic_context.project_id
        updates["workspace_dir"] = None
    elif topic_context.authorized_path:
        from app.services.workspace.file_watch_service import resolve_watchable_workspace_path

        try:
            resolved_path = resolve_watchable_workspace_path(topic_context.authorized_path)
        except ValueError as exc:
            raise ChannelWorkspaceSyncError(str(exc)) from exc
        updates["project_id"] = None
        updates["workspace_dir"] = resolved_path

    return await _apply_chat_workspace_updates(chat, updates)
