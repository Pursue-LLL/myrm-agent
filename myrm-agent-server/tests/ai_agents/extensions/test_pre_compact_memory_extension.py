"""Tests for PreCompactMemoryExtension callback behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import HumanMessage
from myrm_agent_harness.agent.context_management.infra.schemas import PreCompactInjection

from app.ai_agents.extensions.pre_compact_memory import PreCompactMemoryExtension


@pytest.fixture
def mock_memory_manager() -> MagicMock:
    return MagicMock()


@pytest.fixture
def extension(mock_memory_manager: MagicMock) -> PreCompactMemoryExtension:
    return PreCompactMemoryExtension(
        enabled=True,
        is_subagent=False,
        channel_name="default",
        memory_manager=mock_memory_manager,
        effective_chat_id="chat-123",
        budget_tokens=1500,
    )


class TestBuildPreCompactCallback:
    def test_returns_none_when_disabled(self, mock_memory_manager: MagicMock) -> None:
        ext = PreCompactMemoryExtension(
            enabled=False,
            is_subagent=False,
            channel_name="default",
            memory_manager=mock_memory_manager,
            effective_chat_id="chat-123",
        )
        assert ext.build_pre_compact_callback() is None

    def test_returns_none_when_no_memory_manager(self) -> None:
        ext = PreCompactMemoryExtension(
            enabled=True,
            is_subagent=False,
            channel_name="default",
            memory_manager=None,
            effective_chat_id="chat-123",
        )
        assert ext.build_pre_compact_callback() is None

    def test_returns_none_for_subagent(self, mock_memory_manager: MagicMock) -> None:
        ext = PreCompactMemoryExtension(
            enabled=True,
            is_subagent=True,
            channel_name="default",
            memory_manager=mock_memory_manager,
            effective_chat_id="chat-123",
        )
        assert ext.build_pre_compact_callback() is None

    def test_returns_callable_when_enabled(self, extension: PreCompactMemoryExtension) -> None:
        cb = extension.build_pre_compact_callback()
        assert cb is not None
        assert callable(cb)


class TestPreCompactCallbackExecution:
    @pytest.mark.asyncio
    async def test_callback_records_ledger_event(self, extension: PreCompactMemoryExtension) -> None:
        injection = PreCompactInjection(
            message=HumanMessage(content="<pre_compact_recall_context>recall</pre_compact_recall_context>"),
            recalled_ids=("mem-1", "mem-2"),
            token_estimate=420,
            query="refactor auth module",
            compaction_tier="compress",
        )
        mock_service = MagicMock()
        mock_service.build_injection = AsyncMock(return_value=injection)

        with patch(
            "app.ai_agents.extensions.pre_compact_memory.MemoryPreCompactService",
            return_value=mock_service,
        ), patch(
            "app.ai_agents.extensions.pre_compact_memory._record_pre_compact_event",
            new_callable=AsyncMock,
        ) as record_event:
            cb = extension.build_pre_compact_callback()
            assert cb is not None
            result = await cb(
                messages=[HumanMessage(content="continue refactor")],
                chat_id="chat-123",
                user_id="user-1",
                compaction_tier="compress",
                token_pressure_ratio=0.82,
                user_goal_hint="refactor auth module",
            )

        assert result is injection
        await asyncio.sleep(0.05)
        record_event.assert_awaited_once_with(chat_id="chat-123", injection=injection)
