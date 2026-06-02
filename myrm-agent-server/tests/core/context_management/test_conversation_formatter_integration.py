"""Conversation Formatter Integration Tests - 真实场景验证

验证Priority-Based Classification和Smart Fallback在真实agent运行中的表现。
"""

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from myrm_agent_harness.agent.context_management.pipeline.base import ProcessorContext
from myrm_agent_harness.agent.context_management.pipeline.processors.compress_processor import (
    CompressProcessor,
)


class TestConversationFormatterIntegration:
    """Test conversation formatter in realistic scenarios."""

    @pytest.mark.asyncio
    async def test_long_conversation_with_priority_compression(self) -> None:
        """Test priority-aware compression in a long conversation."""
        # Simulate a long conversation with mixed priority messages
        messages = [
            HumanMessage(content="User query 1"),  # CRITICAL_USER
            AIMessage(content="Thinking about query 1..."),  # MEDIUM
            AIMessage(content="Calling search", tool_calls=[{"name": "search", "args": {"query": "q1"}, "id": "call_1"}]),
            ToolMessage(content="Search result " + "x" * 10000, tool_call_id="call_1"),  # LOW (success)
            AIMessage(content="Response to query 1"),
            HumanMessage(content="Follow-up query 2"),  # CRITICAL_USER
            AIMessage(content="More thinking..."),  # MEDIUM
            AIMessage(content="Calling another search", tool_calls=[{"name": "search", "args": {"query": "q2"}, "id": "call_2"}]),
            ToolMessage(content="[ERROR] Connection timeout", tool_call_id="call_2"),  # HIGH (error)
            AIMessage(content="Let me retry..."),
            AIMessage(content="Final response"),  # CRITICAL_FINAL (last iteration)
        ]

        processor = CompressProcessor(
            max_context_tokens=20000,
            keep_recent_calls=1,
            compress_min_save=100,
        )

        context = ProcessorContext(
            messages=messages,
            user_query="Follow-up query 2",
            chat_id="test_chat",
            user_id="test_user",
        )

        result = await processor.process(context)

        # Verify CRITICAL messages are preserved
        human_msgs = [m for m in result.messages if isinstance(m, HumanMessage)]
        assert len(human_msgs) == 2, "All human messages should be preserved"

        final_ai_msgs = [m for m in result.messages if isinstance(m, AIMessage) and "Final response" in str(m.content)]
        assert len(final_ai_msgs) == 1, "Final AI message should be preserved"

        # Verify LOW priority (success) was compressed
        tool_msgs = [m for m in result.messages if isinstance(m, ToolMessage)]
        success_tool = [m for m in tool_msgs if "Search result" in str(m.content)[:50]]
        if success_tool:
            # Should be compressed (LOW priority)
            assert "COMPACTED:" in str(success_tool[0].content) or len(str(success_tool[0].content)) < 1000, (
                "LOW priority tool result should be compressed"
            )

        # Verify HIGH priority (error) was preserved
        error_tool = [m for m in tool_msgs if "[ERROR]" in str(m.content)]
        if error_tool:
            # Should NOT be compressed (HIGH priority)
            assert "Connection timeout" in str(error_tool[0].content), "HIGH priority error should be preserved"

        # Verify tokens were saved
        assert result.tokens_saved > 0, "Should save tokens by compressing LOW priority messages"

    @pytest.mark.asyncio
    async def test_extreme_token_overflow_triggers_fallback(self) -> None:
        """Test smart fallback triggers when tokens severely exceed budget."""
        # Create a scenario that will trigger fallback
        messages = []

        # Add many large tool results to exceed budget
        for i in range(20):
            messages.append(HumanMessage(content=f"Query {i}"))
            messages.append(AIMessage(content=f"Call {i}", tool_calls=[{"name": "search", "args": {}, "id": f"call_{i}"}]))
            messages.append(ToolMessage(content=f"Result {i} " + "x" * 8000, tool_call_id=f"call_{i}"))

        messages.append(AIMessage(content="Final answer"))

        # Use small max_context_tokens to force fallback
        processor = CompressProcessor(
            max_context_tokens=15000,
            keep_recent_calls=1,
            compress_min_save=100,
        )
        config = processor.config

        context = ProcessorContext(
            messages=messages,
            user_query="Query 19",
            chat_id="test_overflow",
            user_id="test_user",
        )

        result = await processor.process(context)

        # Verify result is within budget
        from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

        final_tokens = estimate_messages_tokens(result.messages)

        # Should be under max_context_tokens (fallback brings it to 90%)
        assert final_tokens < config.max_context_tokens, (
            f"Should respect max budget after fallback: {final_tokens} < {config.max_context_tokens}"
        )

        # Verify tokens were saved
        assert result.tokens_saved > 0, "Should save significant tokens via compression + fallback"

        # Verify CRITICAL messages (human + final AI) are preserved
        human_count = sum(1 for m in result.messages if isinstance(m, HumanMessage))
        assert human_count >= 1, "At least some human messages should be preserved"

        final_ai = [m for m in result.messages if isinstance(m, AIMessage) and "Final answer" in str(m.content)]
        assert len(final_ai) == 1, "Final AI message should be preserved"
