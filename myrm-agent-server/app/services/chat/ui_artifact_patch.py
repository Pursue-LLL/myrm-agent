"""Cross-turn UI artifact data persistence for update_ui_data_tool.

[INPUT]
- app.core.utils.ui_data_merge::deep_merge_ui_data (POS: A2UI binding dict deep-merge)
- app.services.chat.chat_service::ChatService (POS: 聊天业务统一入口)
- app.database.dto::MessageDTO (POS: 消息领域对象)

[OUTPUT]
- merge_ui_artifact_data_in_extra_data: in-memory uiArtifacts data merge
- patch_ui_artifact_data_by_surface_id: locate host message and persist merge
- patch_ui_artifact_data_updates: batch cross-turn patches at stream finalize

[POS]
Chat business layer. Persists cross-turn update_ui_data_tool data_update events onto
the host assistant message so reload restores merged A2UI bindings.
"""

from __future__ import annotations

import logging

from app.core.utils.ui_data_merge import deep_merge_ui_data
from app.database.dto import MessageDTO
from app.services.chat.chat_service import ChatService

logger = logging.getLogger(__name__)


def merge_ui_artifact_data_in_extra_data(
    extra_data: dict[str, object],
    surface_id: str,
    updates: dict[str, object],
) -> bool:
    """Deep-merge updates into uiArtifacts[].data for surface_id. Returns True if patched."""
    raw_artifacts = extra_data.get("uiArtifacts")
    if not isinstance(raw_artifacts, list):
        return False
    for artifact in raw_artifacts:
        if not isinstance(artifact, dict):
            continue
        if artifact.get("surface_id") != surface_id:
            continue
        existing_data = artifact.get("data")
        if not isinstance(existing_data, dict):
            existing_data = {}
        artifact["data"] = deep_merge_ui_data(existing_data, updates)
        return True
    return False


def _find_host_message_for_surface(
    messages: list[MessageDTO],
    surface_id: str,
) -> MessageDTO | None:
    for message in reversed(messages):
        if message.role != "assistant":
            continue
        extra_data = message.extra_data
        if not isinstance(extra_data, dict):
            continue
        raw_artifacts = extra_data.get("uiArtifacts")
        if not isinstance(raw_artifacts, list):
            continue
        for artifact in raw_artifacts:
            if isinstance(artifact, dict) and artifact.get("surface_id") == surface_id:
                return message
    return None


async def patch_ui_artifact_data_by_surface_id(
    chat_id: str,
    surface_id: str,
    updates: dict[str, object],
) -> bool:
    """Find host message by surface_id and persist merged uiArtifacts data."""
    messages = await ChatService.get_all_messages(chat_id)
    host_message = _find_host_message_for_surface(messages, surface_id)
    if host_message is None:
        logger.warning(
            "Cross-turn ui data_update ignored: surface_id=%s chat_id=%s (no host message)",
            surface_id,
            chat_id,
        )
        return False

    extra_data = dict(host_message.extra_data or {})
    if not merge_ui_artifact_data_in_extra_data(extra_data, surface_id, updates):
        return False

    await ChatService.update_message_extra_data(host_message.id, extra_data)
    logger.info(
        "Cross-turn ui data_update persisted: surface_id=%s host_message_id=%s chat_id=%s",
        surface_id,
        host_message.id,
        chat_id,
    )
    return True


async def patch_ui_artifact_data_updates(
    chat_id: str,
    updates: list[tuple[str, dict[str, object]]],
) -> None:
    """Apply multiple cross-turn data_update patches (merge per surface_id)."""
    if not updates:
        return
    merged_by_surface: dict[str, dict[str, object]] = {}
    for surface_id, patch in updates:
        existing = merged_by_surface.get(surface_id)
        if existing is None:
            merged_by_surface[surface_id] = dict(patch)
        else:
            merged_by_surface[surface_id] = deep_merge_ui_data(existing, patch)
    for surface_id, patch in merged_by_surface.items():
        await patch_ui_artifact_data_by_surface_id(chat_id, surface_id, patch)
