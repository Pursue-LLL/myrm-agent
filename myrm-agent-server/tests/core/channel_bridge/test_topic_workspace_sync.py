"""Tests for channel topic workspace sync into chat SSOT."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.types import TopicContext
from app.core.channel_bridge.executor_helpers.topic_workspace_sync import (
    ChannelWorkspaceSyncError,
    sync_channel_chat_workspace,
    topic_declares_workspace,
)
from app.database.dto import ChatDTO


def _channel_chat(**overrides: object) -> ChatDTO:
    now = datetime.now(timezone.utc)
    base = {
        "id": "chat-1",
        "source": "wechat",
        "channel_session_key": "wechat:group-1",
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return ChatDTO.model_validate(base)


def test_topic_declares_workspace() -> None:
    assert not topic_declares_workspace(None)
    assert not topic_declares_workspace(TopicContext(topic_id="t1"))
    assert topic_declares_workspace(
        TopicContext(topic_id="t1", project_id="proj-1"),
    )


@pytest.mark.asyncio
async def test_sync_channel_chat_workspace_project() -> None:
    chat = MagicMock()
    chat.id = "chat-1"
    chat.project_id = None
    chat.workspace_dir = None
    chat.model_copy = MagicMock(
        return_value=MagicMock(project_id="proj-1", workspace_dir=None),
    )

    project = MagicMock()
    project.workspace_path = "/tmp/vault"

    with (
        patch(
            "app.services.project.project_service.ProjectService.get_project",
            new_callable=AsyncMock,
            return_value=project,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.update_chat_fields",
            new_callable=AsyncMock,
        ) as mock_update,
    ):
        updated = await sync_channel_chat_workspace(
            chat,
            TopicContext(topic_id="t1", project_id="proj-1"),
        )

    mock_update.assert_awaited_once_with(
        "chat-1",
        {"project_id": "proj-1", "workspace_dir": None},
    )
    assert updated.project_id == "proj-1"


@pytest.mark.asyncio
async def test_sync_channel_chat_workspace_missing_project_raises() -> None:
    chat = MagicMock()
    chat.id = "chat-1"
    chat.project_id = None
    chat.workspace_dir = None

    with patch(
        "app.services.project.project_service.ProjectService.get_project",
        new_callable=AsyncMock,
        return_value=None,
    ):
        with pytest.raises(ChannelWorkspaceSyncError):
            await sync_channel_chat_workspace(
                chat,
                TopicContext(topic_id="t1", project_id="missing"),
            )


@pytest.mark.asyncio
async def test_sync_channel_chat_workspace_authorized_path() -> None:
    chat = MagicMock()
    chat.id = "chat-2"
    chat.project_id = "old-proj"
    chat.workspace_dir = "/old/path"

    with (
        patch(
            "app.services.workspace.file_watch_service.resolve_watchable_workspace_path",
            return_value="/resolved/vault",
        ),
        patch(
            "app.services.chat.chat_service.ChatService.update_chat_fields",
            new_callable=AsyncMock,
        ) as mock_update,
    ):
        await sync_channel_chat_workspace(
            chat,
            TopicContext(topic_id="t1", authorized_path="~/vault"),
        )

    mock_update.assert_awaited_once_with(
        "chat-2",
        {"project_id": None, "workspace_dir": "/resolved/vault"},
    )


@pytest.mark.asyncio
async def test_sync_channel_chat_workspace_clears_on_unbind() -> None:
    chat = _channel_chat(id="chat-3", project_id="proj-old", workspace_dir="/old/vault")

    with patch(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        new_callable=AsyncMock,
    ) as mock_update:
        updated = await sync_channel_chat_workspace(
            chat,
            TopicContext(topic_id="t1"),
        )

    mock_update.assert_awaited_once_with(
        "chat-3",
        {"project_id": None, "workspace_dir": None},
    )
    assert updated.project_id is None
    assert updated.workspace_dir is None


@pytest.mark.asyncio
async def test_sync_channel_chat_workspace_noop_when_already_cleared() -> None:
    chat = _channel_chat(id="chat-4")

    with patch(
        "app.services.chat.chat_service.ChatService.update_chat_fields",
        new_callable=AsyncMock,
    ) as mock_update:
        updated = await sync_channel_chat_workspace(
            chat,
            TopicContext(topic_id="t1"),
        )

    mock_update.assert_not_called()
    assert updated.project_id is None
    assert updated.workspace_dir is None


@pytest.mark.asyncio
async def test_sync_then_resolve_effective_workspace_matches_project_vault() -> None:
    chat = _channel_chat(id="chat-int-1")
    vault_path = "/tmp/channel-topic-vault"

    project = MagicMock()
    project.workspace_path = vault_path

    with (
        patch(
            "app.services.project.project_service.ProjectService.get_project",
            new_callable=AsyncMock,
            return_value=project,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.update_chat_fields",
            new_callable=AsyncMock,
        ),
    ):
        synced = await sync_channel_chat_workspace(
            chat,
            TopicContext(topic_id="t1", project_id="proj-int"),
        )

    from app.services.chat.effective_workspace import resolve_effective_chat_workspace

    with patch(
        "app.services.project.project_service.ProjectService.get_project",
        new_callable=AsyncMock,
        return_value=project,
    ):
        resolved = await resolve_effective_chat_workspace(synced, jit_fallback=False)

    assert synced.project_id == "proj-int"
    assert synced.workspace_dir is None
    assert resolved == vault_path
