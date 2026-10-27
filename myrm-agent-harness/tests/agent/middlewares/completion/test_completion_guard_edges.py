"""Edge-path tests for CompletionGuard middleware and the directive it leaves for the model."""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.middlewares.completion import is_mutating_tool
from myrm_agent_harness.agent.middlewares.completion.completion_directive import (
    BlockReasons,
    render_completion_directive,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard import reset_completion_guard


class TestIsMutatingTool:
    def test_mutating_tool_true(self) -> None:
        assert is_mutating_tool("file_write_tool") is True

    def test_non_mutating_tool_false(self) -> None:
        assert is_mutating_tool("file_read_tool") is False


class TestDirectiveBranches:
    def setup_method(self) -> None:
        reset_completion_guard()

    def test_evidence_reason_branch(self) -> None:
        result = render_completion_directive(
            BlockReasons(evidence="freshness query without evidence tools"), records=[], workspace_root=None
        )
        assert "CRITICAL COMPLETION CHECK" in result
        assert "freshness query without evidence tools" in result

    def test_deliverable_write_reason_branch(self) -> None:
        result = render_completion_directive(
            BlockReasons(deliverable_write="claimed file write without tool call"), records=[], workspace_root=None
        )
        assert "CRITICAL COMPLETION CHECK" in result
        assert "claimed file write without tool call" in result


class TestCompletionGuardEdgeStates:
    """aafter_model guard branches for empty / missing-AI-message states."""

    def setup_method(self) -> None:
        from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
            CompletionGuard,
        )

        self.guard = CompletionGuard()
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_empty_messages_returns_none(self) -> None:
        result = await self.guard.aafter_model({"messages": []}, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_messages_key_returns_none(self) -> None:
        result = await self.guard.aafter_model({}, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_ai_message_returns_none(self) -> None:
        from langchain_core.messages import HumanMessage

        state = {"messages": [HumanMessage(content="hello")]}
        result = await self.guard.aafter_model(state, None)
        assert result is None

    @pytest.mark.asyncio
    async def test_ai_message_without_tool_calls_not_blocked(self) -> None:
        state = {"messages": [AIMessage(content="Done, no files touched.")]}
        result = await self.guard.aafter_model(state, None)
        assert result is None
