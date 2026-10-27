"""Tests for channel executor history helpers."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.code_execution import create_workspace_service
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.channel_bridge.executor_helpers.history import (
    load_history_without_persist,
    persist_and_load_history,
    persist_assistant_message,
)
from app.services.agent.params.workspace_resolve import default_chat_workspace_path
from app.services.chat.chat_helpers import ChannelHistoryEntry
from app.services.context.context_assembly import ContextAssemblyService

_OVERSIZED_PASTE = "meeting-line: the decision was to keep watching and review next week\n" * 400


@pytest.mark.asyncio
async def test_persist_and_load_history_commits_chat() -> None:
    created = datetime(2026, 7, 13, tzinfo=timezone.utc)
    history_entry = ChannelHistoryEntry(role="human", content="Hi", created_at=created)
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "app.database.connection.get_session",
        ) as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_or_create_channel_chat",
            new_callable=AsyncMock,
        ) as mock_get_chat,
        patch(
            "app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate",
            new_callable=AsyncMock,
        ) as mock_stale_gate,
        patch(
            "app.services.chat.chat_service.ChatService.append_message",
            new_callable=AsyncMock,
        ) as mock_append,
        patch(
            "app.services.chat.chat_service.ChatService.load_channel_history",
            new_callable=AsyncMock,
            return_value=[history_entry],
        ),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False
        mock_chat = MagicMock()
        mock_chat.id = "chat-1"
        mock_chat.project_id = None
        mock_chat.workspace_dir = None
        mock_get_chat.return_value = mock_chat

        chat_id, history = await persist_and_load_history(
            "telegram:peer",
            "telegram",
            "Hello",
            created,
            "UTC",
            agent_id="agent-telegram",
        )

    assert chat_id == "chat-1"
    assert history == [history_entry]
    mock_stale_gate.assert_awaited_once_with(
        "chat-1",
        agent_id="agent-telegram",
    )
    mock_append.assert_awaited_once()
    mock_session.commit.assert_awaited_once()


async def _persisted_with_spill_workspace(chat_id: str) -> object:
    """The ``spill_workspace`` ``persist_and_load_history`` hands to ``append_message`` for a chat with this id."""
    created = datetime(2026, 7, 13, tzinfo=timezone.utc)
    mock_session = AsyncMock()
    chat = MagicMock()
    chat.id = chat_id
    chat.project_id = None
    chat.workspace_dir = None

    with (
        patch("app.database.connection.get_session") as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_or_create_channel_chat",
            new_callable=AsyncMock,
            return_value=chat,
        ),
        patch("app.services.chat.stale_compact_gate.run_pre_reply_stale_compact_gate", new_callable=AsyncMock),
        patch("app.services.chat.chat_service.ChatService.append_message", new_callable=AsyncMock) as mock_append,
        patch("app.services.chat.chat_service.ChatService.load_channel_history", new_callable=AsyncMock, return_value=[]),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False
        await persist_and_load_history("telegram:peer", "telegram", "Hello", created, "UTC")

    return mock_append.await_args.kwargs["spill_workspace"]


@pytest.mark.asyncio
async def test_persist_and_load_history_spills_into_the_workspace_the_agent_runs_in() -> None:
    assert await _persisted_with_spill_workspace("chat-1") == default_chat_workspace_path("chat-1")


@pytest.mark.asyncio
async def test_persist_and_load_history_keeps_the_default_spill_dir_for_an_id_that_cannot_name_a_workspace(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.core.channel_bridge.executor_helpers.history"):
        assert await _persisted_with_spill_workspace("a/b") is None

    assert "cannot name a workspace directory" in caplog.text


@pytest.mark.asyncio
async def test_an_oversized_paste_is_parked_where_the_harness_runs_the_agent(db_session: AsyncSession) -> None:
    """The agent reads the paste back only if the file sits inside its workspace, which the harness derives itself."""
    del db_session
    chat_id, _history = await persist_and_load_history("test:oversized-paste", "test", _OVERSIZED_PASTE, datetime.now(UTC), "UTC")

    workspaces = create_workspace_service(root_dir=Path(ContextAssemblyService.harness_storage_root()).expanduser().resolve())
    workspace = await workspaces.get_or_create(session_id=f"chat_{chat_id}")
    agent_workspace = Path(workspaces.get_workspace_absolute_path(workspace)).resolve()

    (parked,) = list((agent_workspace / ".myrm" / "spillover").glob("payload_*.md"))
    assert parked.read_text(encoding="utf-8") == _OVERSIZED_PASTE


@pytest.mark.asyncio
async def test_load_history_without_persist_returns_empty_when_missing() -> None:
    mock_session = AsyncMock()

    with (
        patch(
            "app.database.connection.get_session",
        ) as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_channel_chat_by_key",
            new_callable=AsyncMock,
            return_value=None,
        ),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False

        chat_id, history = await load_history_without_persist("missing:key")

    assert chat_id == ""
    assert history == []


@pytest.mark.asyncio
async def test_load_history_without_persist_returns_history() -> None:
    created = datetime(2026, 7, 13, tzinfo=timezone.utc)
    history_entry = ChannelHistoryEntry(role="human", content="Hi", created_at=created)
    mock_session = AsyncMock()
    mock_chat = MagicMock()
    mock_chat.id = "chat-9"
    mock_chat.project_id = None
    mock_chat.workspace_dir = None

    with (
        patch("app.database.connection.get_session") as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.get_channel_chat_by_key",
            new_callable=AsyncMock,
            return_value=mock_chat,
        ),
        patch(
            "app.services.chat.chat_service.ChatService.load_channel_history",
            new_callable=AsyncMock,
            return_value=[history_entry],
        ),
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False

        chat_id, history = await load_history_without_persist("telegram:peer")

    assert chat_id == "chat-9"
    assert history == [history_entry]


@pytest.mark.asyncio
async def test_persist_assistant_message_appends() -> None:
    mock_session = AsyncMock()
    mock_session.commit = AsyncMock()

    with (
        patch(
            "app.database.connection.get_session",
        ) as mock_get_session,
        patch(
            "app.services.chat.chat_service.ChatService.append_message",
            new_callable=AsyncMock,
        ) as mock_append,
    ):
        mock_get_session.return_value.__aenter__.return_value = mock_session
        mock_get_session.return_value.__aexit__.return_value = False

        await persist_assistant_message("chat-1", "Reply", timezone="Asia/Shanghai")

    mock_append.assert_awaited_once()
    mock_session.commit.assert_awaited_once()
