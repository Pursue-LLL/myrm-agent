"""Tests for ArchiveCheckpointMemoryExtension."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.context_management.archive_checkpoint.types import ArchiveCheckpointRecord

from app.ai_agents.extensions.archive_checkpoint_memory import ArchiveCheckpointMemoryExtension


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def extension(mock_memory_manager: MagicMock) -> ArchiveCheckpointMemoryExtension:
    return ArchiveCheckpointMemoryExtension(
        enabled=True,
        is_subagent=False,
        channel_name="default",
        memory_manager=mock_memory_manager,
        effective_chat_id="chat-123",
    )


class TestBuildArchiveCheckpointStore:
    def test_returns_none_when_disabled(self, mock_memory_manager: MagicMock) -> None:
        ext = ArchiveCheckpointMemoryExtension(
            enabled=False,
            is_subagent=False,
            channel_name="default",
            memory_manager=mock_memory_manager,
            effective_chat_id="chat-123",
        )
        assert ext.build_archive_checkpoint_store() is None

    def test_returns_store_when_enabled(self, extension: ArchiveCheckpointMemoryExtension) -> None:
        store = extension.build_archive_checkpoint_store()
        assert store is not None


class TestArchiveCheckpointNotifier:
    @pytest.mark.asyncio
    async def test_notifier_records_ledger_event(self, extension: ArchiveCheckpointMemoryExtension) -> None:
        record = ArchiveCheckpointRecord(
            memory_id="mem-1",
            tool_name="grep_tool",
            archive_path=".context/chat-123/compacted/result.txt",
            summary="summary body",
            chat_id="chat-123",
        )
        notifier = extension.build_archive_checkpoint_notifier()
        assert notifier is not None

        with patch(
            "app.ai_agents.extensions.archive_checkpoint_memory._record_archive_checkpoint_event",
            new_callable=AsyncMock,
        ) as record_event, patch(
            "app.ai_agents.extensions.archive_checkpoint_memory._dispatch_archive_checkpoint_status",
            new_callable=AsyncMock,
        ) as dispatch_status:
            await notifier(record, None)
            dispatch_status.assert_awaited_once()
            await asyncio.sleep(0)
            record_event.assert_awaited_once()
