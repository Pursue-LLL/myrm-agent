"""Tests for ZeroCostMemoryExtension eviction callback behavior."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, ToolMessage
from myrm_agent_harness.agent.context_management.infra.schemas import EvictedToolCall

from app.ai_agents.extensions.zero_cost_memory import ZeroCostMemoryExtension


@pytest.fixture
def mock_memory_manager():
    mm = MagicMock()
    mm.user_id = "test-user"
    return mm


@pytest.fixture
def mock_extractor_llm():
    return MagicMock()


@pytest.fixture
def extension(mock_memory_manager, mock_extractor_llm):
    return ZeroCostMemoryExtension(
        enable_memory_auto_extraction=True,
        is_subagent=False,
        channel_name="default",
        memory_manager=mock_memory_manager,
        effective_chat_id="chat-123",
        extractor_llm=mock_extractor_llm,
    )


class TestBuildEvictionCallback:
    def test_returns_none_when_disabled(self, mock_memory_manager, mock_extractor_llm):
        ext = ZeroCostMemoryExtension(
            enable_memory_auto_extraction=False,
            is_subagent=False,
            channel_name="default",
            memory_manager=mock_memory_manager,
            effective_chat_id="chat-123",
            extractor_llm=mock_extractor_llm,
        )
        assert ext.build_eviction_callback() is None

    def test_returns_none_when_no_memory_manager(self, mock_extractor_llm):
        ext = ZeroCostMemoryExtension(
            enable_memory_auto_extraction=True,
            is_subagent=False,
            channel_name="default",
            memory_manager=None,
            effective_chat_id="chat-123",
            extractor_llm=mock_extractor_llm,
        )
        assert ext.build_eviction_callback() is None

    def test_returns_none_for_subagent(self, mock_memory_manager, mock_extractor_llm):
        ext = ZeroCostMemoryExtension(
            enable_memory_auto_extraction=True,
            is_subagent=True,
            channel_name="default",
            memory_manager=mock_memory_manager,
            effective_chat_id="chat-123",
            extractor_llm=mock_extractor_llm,
        )
        assert ext.build_eviction_callback() is None

    def test_returns_none_for_subagent_channel(self, mock_memory_manager, mock_extractor_llm):
        ext = ZeroCostMemoryExtension(
            enable_memory_auto_extraction=True,
            is_subagent=False,
            channel_name="subagent",
            memory_manager=mock_memory_manager,
            effective_chat_id="chat-123",
            extractor_llm=mock_extractor_llm,
        )
        assert ext.build_eviction_callback() is None

    def test_returns_callable_when_enabled(self, extension):
        cb = extension.build_eviction_callback()
        assert cb is not None
        assert callable(cb)


class TestEvictionCallbackUsesOriginalContent:
    @pytest.mark.asyncio
    async def test_callback_passes_original_content_to_extractor(self, extension):
        """The eviction callback must use EvictedToolCall.original_content, NOT tool_msg.content."""
        ai_msg = AIMessage(
            content="Let me read that file", tool_calls=[{"id": "tc1", "name": "file_read", "args": {"path": "config.yaml"}}]
        )
        tool_msg = ToolMessage(content="COMPACTED: file_read [config.yaml] 800→25 tokens", tool_call_id="tc1", name="file_read")

        original_content = "database:\n  host: localhost\n  port: 5432\n  max_connections: 100"

        evicted = [EvictedToolCall(ai_msg=ai_msg, tool_msg=tool_msg, original_content=original_content)]

        mock_result = MagicMock()
        mock_result.memories = []
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract = AsyncMock(return_value=mock_result)

        with (
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.MemoryExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.persist_extracted_memories",
                new_callable=AsyncMock,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func",
                return_value=AsyncMock(),
            ),
        ):
            cb = extension.build_eviction_callback()
            assert cb is not None
            await cb(evicted, "user wants to configure database")

            await asyncio.sleep(0.2)
            pending = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
            for t in pending:
                try:
                    await asyncio.wait_for(t, timeout=2.0)
                except (TimeoutError, Exception):
                    pass

            mock_extractor_instance.extract.assert_called_once()
            call_args = mock_extractor_instance.extract.call_args
            messages = call_args[0][0]

            tool_result_msg = next((m for m in messages if m["role"] == "user" and "ToolResult" in m["content"]), None)
            assert tool_result_msg is not None
            assert original_content in tool_result_msg["content"]
            assert "COMPACTED" not in tool_result_msg["content"]


class TestEvictionCallbackPublishesSSE:
    @pytest.mark.asyncio
    async def test_publishes_memory_operation_sse_on_extraction(self, extension):
        """After extracting memories, the callback must publish an SSE event."""
        ai_msg = AIMessage(content="Reading config", tool_calls=[{"id": "tc1", "name": "read", "args": {}}])
        tool_msg = ToolMessage(content="compacted", tool_call_id="tc1", name="read")
        evicted = [EvictedToolCall(ai_msg=ai_msg, tool_msg=tool_msg, original_content="host: localhost")]

        mock_memory = MagicMock()
        mock_memory.content = "User prefers dark mode"
        mock_result = MagicMock()
        mock_result.memories = [mock_memory]
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract = AsyncMock(return_value=mock_result)

        mock_publish = MagicMock()
        mock_event_bus = MagicMock()
        mock_event_bus.publish = mock_publish

        with (
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.MemoryExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.persist_extracted_memories",
                new_callable=AsyncMock,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.event.app_event_bus.get_event_bus",
                return_value=mock_event_bus,
            ),
        ):
            cb = extension.build_eviction_callback()
            assert cb is not None
            await cb(evicted, "user goal")

            await asyncio.sleep(0.2)
            pending = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
            for t in pending:
                try:
                    await asyncio.wait_for(t, timeout=2.0)
                except (TimeoutError, Exception):
                    pass

            mock_publish.assert_called_once()
            event = mock_publish.call_args[0][0]
            assert event.data["operation"] == "auto_memory_extracted"
            assert event.data["count"] == 1
            assert event.data["source"] == "eviction"
            assert event.data["chat_id"] == "chat-123"

    @pytest.mark.asyncio
    async def test_no_sse_when_no_memories_extracted(self, extension):
        """No SSE event should be published when extraction yields no memories."""
        ai_msg = AIMessage(content="reading", tool_calls=[{"id": "tc1", "name": "read", "args": {}}])
        tool_msg = ToolMessage(content="compacted", tool_call_id="tc1", name="read")
        evicted = [EvictedToolCall(ai_msg=ai_msg, tool_msg=tool_msg, original_content="empty")]

        mock_result = MagicMock()
        mock_result.memories = []
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract = AsyncMock(return_value=mock_result)

        mock_publish = MagicMock()
        mock_event_bus = MagicMock()
        mock_event_bus.publish = mock_publish

        with (
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.MemoryExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.persist_extracted_memories",
                new_callable=AsyncMock,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.event.app_event_bus.get_event_bus",
                return_value=mock_event_bus,
            ),
        ):
            cb = extension.build_eviction_callback()
            assert cb is not None
            await cb(evicted, "user goal")

            await asyncio.sleep(0.2)
            pending = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
            for t in pending:
                try:
                    await asyncio.wait_for(t, timeout=2.0)
                except (TimeoutError, Exception):
                    pass

            mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_sse_failure_does_not_break_extraction(self, extension):
        """SSE publish failure must not affect the memory extraction flow."""
        ai_msg = AIMessage(content="reading", tool_calls=[{"id": "tc1", "name": "read", "args": {}}])
        tool_msg = ToolMessage(content="compacted", tool_call_id="tc1", name="read")
        evicted = [EvictedToolCall(ai_msg=ai_msg, tool_msg=tool_msg, original_content="data")]

        mock_memory = MagicMock()
        mock_result = MagicMock()
        mock_result.memories = [mock_memory]
        mock_extractor_instance = MagicMock()
        mock_extractor_instance.extract = AsyncMock(return_value=mock_result)

        mock_persist = AsyncMock()

        mock_event_bus = MagicMock()
        mock_event_bus.publish = MagicMock(side_effect=RuntimeError("SSE bus down"))

        with (
            patch(
                "myrm_agent_harness.toolkits.memory.strategies.extractor.MemoryExtractor",
                return_value=mock_extractor_instance,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.persist_extracted_memories",
                mock_persist,
            ),
            patch(
                "myrm_agent_harness.agent._internals.memory_extraction.create_extraction_llm_func",
                return_value=AsyncMock(),
            ),
            patch(
                "app.services.event.app_event_bus.get_event_bus",
                return_value=mock_event_bus,
            ),
        ):
            cb = extension.build_eviction_callback()
            assert cb is not None
            await cb(evicted, "user goal")

            await asyncio.sleep(0.2)
            pending = [t for t in asyncio.all_tasks() if not t.done() and t != asyncio.current_task()]
            for t in pending:
                try:
                    await asyncio.wait_for(t, timeout=2.0)
                except (TimeoutError, Exception):
                    pass

            mock_persist.assert_called_once()
